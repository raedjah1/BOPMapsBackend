import os
import asyncio
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import b2sdk.v2 as b2
from dotenv import load_dotenv
import re
import glob
import redis
import ssl
load_dotenv()

info = b2.InMemoryAccountInfo()
b2_api = b2.B2Api(info)
b2_api.authorize_account("production", os.getenv("B2_KEY_ID"), os.getenv("B2_APPLICATION_KEY"))
b2_bucket = b2_api.get_bucket_by_name(os.getenv("B2_BUCKET_NAME"))

# Initialize Redis client (ElastiCache)
redis_client = redis.Redis(
    host=os.getenv("ELASTICACHE_HOST"),
    port=os.getenv("ELASTICACHE_PORT"),
    username=os.getenv("ELASTICACHE_USERNAME"),
    password=os.getenv("ELASTICACHE_PASSWORD"),
    ssl=False,
    ssl_cert_reqs=None,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5
)

class AsyncHLSFileWatcher(FileSystemEventHandler):
    def __init__(self, directory_to_watch, num_workers=6, stream_timeout=180):
        self.directory_to_watch = directory_to_watch
        self.upload_queue = asyncio.Queue()
        self.last_update_time = {}
        self.num_workers = num_workers
        self.m3u8_files = {}
        self.stream_timeout = stream_timeout
        self.loop = asyncio.get_event_loop()  # Get event loop reference

    def on_any_event(self, event):
        if event.is_directory:
            return
        
        if event.event_type in ['created', 'modified', 'moved']:
            file_path = event.dest_path if (event.event_type == 'moved' or event.event_type == 'modified') else event.src_path

            if file_path.endswith('.m3u8'):
                if 'index' not in os.path.basename(file_path).lower():
                    self.loop.create_task(self.queue_file(file_path))
                    print(f"Non-index M3U8 file queued for direct upload: {file_path}")
                else:
                    self.loop.create_task(self.process_m3u8(file_path))

    async def queue_file(self, file_path):
        await self.upload_queue.put(file_path)
        print(f"File queued: {file_path}")

    async def process_m3u8(self, m3u8_path):
        await asyncio.sleep(0.1)  # Short delay to ensure file writing is complete
        if m3u8_path not in self.m3u8_files:
            self.m3u8_files[m3u8_path] = set()
            print(f"New M3U8 file detected: {m3u8_path}")
        
        await self.check_m3u8_updates(m3u8_path)

    async def check_m3u8_updates(self, m3u8_path):
        try:
            with open(m3u8_path, 'r') as file:
                content = file.read()
            
            current_ts_files = set(line.strip() for line in content.splitlines() if line.strip().endswith('.ts'))
            new_ts_files = current_ts_files - self.m3u8_files.get(m3u8_path, set())
            
            if new_ts_files:
                print(f"New TS files in {m3u8_path}: {', '.join(new_ts_files)}")
                for ts_file in new_ts_files:
                    ts_path = os.path.join(os.path.dirname(m3u8_path), ts_file)
                    if os.path.exists(ts_path):
                        await self.upload_queue.put(ts_path)
                        print(f"Queued for upload: {ts_path}")
                    else:
                        print(f"Warning: TS file {ts_file} not found in directory.")

                # Check if m3u8 file is in redis
                redis_key = os.path.relpath(m3u8_path, self.directory_to_watch)
                cached_content = redis_client.get(redis_key)
                
                if not cached_content:
                    # If it is not, then upload it to redis and put in upload queue
                    redis_client.set(redis_key, content)
                    await self.upload_queue.put(m3u8_path)
                else:                    
                    # Check for the last updated ts file in the playlist from redis
                    cached_ts_files = [line.strip() for line in cached_content.splitlines() if line.strip().endswith('.ts')]
                    last_cached_ts = cached_ts_files[-1] if cached_ts_files else None

                    print(f"Last cached TS file: {last_cached_ts}")
                    
                    # Find all local ts files (and EXTINFO line above them) that are after the last updated ts file
                    new_content_lines = []
                    add_lines = False

                    for line in content.splitlines():
                        if add_lines:
                            new_content_lines.append(line)
                        # Since we are using sytem time for .ts naming:
                        elif not line.startswith('#') and int(line.strip().split('.')[0]) >= int(last_cached_ts.split('.')[0]):
                            add_lines = True
                    
                    # Add those files to manifest and upload back to redis and put in upload queue
                    if new_content_lines:
                        updated_content = cached_content + '\n'.join(new_content_lines) + '\n'
                        redis_client.set(redis_key, updated_content)

                        await self.upload_queue.put((redis_key, updated_content.encode('utf-8'), 'application/vnd.apple.mpegurl'))
                        print(f"Queued for upload with redis key: {redis_key}")
                    
                print(f"Queued for upload: {m3u8_path}")
                self.m3u8_files[m3u8_path].update(new_ts_files)
                self.last_update_time[m3u8_path] = time.time()
        except Exception as e:
            print(f"Error processing {m3u8_path}: {str(e)}")

    async def upload_worker(self):
        print(f"Upload worker started with ID: {id(self)}")
        try:
            while True:
                print("Worker waiting for task...")
                file_or_tuple = await self.upload_queue.get()
                print(f"Worker received task")
                
                if isinstance(file_or_tuple, tuple):
                    print(f"Uploading with redis key: {file_or_tuple[0]}")
                    file_name, content, content_type = file_or_tuple
                    start_time = time.time()
                    try:
                        uploaded_file = await self.loop.run_in_executor(
                            None,
                            lambda: b2_bucket.upload_bytes(
                                data_bytes=content,
                                file_name=file_name,
                                content_type=content_type
                            )
                        )

                        end_time = time.time()
                        upload_duration = end_time - start_time

                        print(f"Uploaded {file_name} to B2 bucket")
                        print(f"Upload time: {upload_duration:.2f} seconds")
                        print(f"-------------------------------------")
                    except Exception as e:
                        print(f"Failed to upload {file_name}: {str(e)}")
                    finally:
                        self.upload_queue.task_done()
                else:
                    print(f"Uploading local file")
                    file_path = file_or_tuple.replace('\\', '/')
                    start_time = time.time()
                    try:
                        content_type = 'video/MP2T' if file_path.endswith('.ts') else 'application/vnd.apple.mpegurl'
                        uploaded_file = await self.loop.run_in_executor(
                            None,
                            lambda: b2_bucket.upload_local_file(
                                local_file=file_path,
                                file_name=os.path.relpath(file_path, self.directory_to_watch),
                                content_type=content_type
                            )
                        )

                        end_time = time.time()
                        upload_duration = end_time - start_time

                        file_size = os.path.getsize(file_path)
                        upload_speed = file_size / upload_duration / 1024 / 1024  # in MB/s

                        # Delete the local file after successful upload
                        if not file_path.endswith('.m3u8'):
                            try:
                                os.remove(file_path)
                                print(f"Successfully deleted local file: {file_path}")
                            except Exception as e:
                                print(f"Failed to delete local file {file_path}: {str(e)}")
                        else:
                            print(f"Keeping m3u8 file: {file_path}")
                        
                        print(f"Uploaded {file_path} to B2 bucket")
                        print(f"Upload time: {upload_duration:.2f} seconds")
                        print(f"File size: {file_size / 1024 / 1024:.2f} MB")
                        print(f"Upload speed: {upload_speed:.2f} MB/s")
                        print(f"-------------------------------------")
                    except Exception as e:
                        print(f"Failed to upload {file_path}: {str(e)}")
                    finally:
                        self.upload_queue.task_done()
        except Exception as e:
            print(f"Worker error: {str(e)}")
            raise

    async def run(self):
        observer = Observer()
        observer.schedule(self, self.directory_to_watch, recursive=True)
        observer.start()
        print(f"Watching directory: {self.directory_to_watch}")

        # Create workers
        self.upload_workers = []
        for i in range(self.num_workers):
            worker = asyncio.create_task(self.upload_worker())
            self.upload_workers.append(worker)
            print(f"Started worker {i+1}")

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Cancelling all tasks...")
            for worker in self.upload_workers:
                worker.cancel()
            observer.stop()
        finally:
            await asyncio.gather(*self.upload_workers, return_exceptions=True)
            observer.join()
            print("All tasks have been cancelled and observer stopped.")

if __name__ == "__main__":
    directory_to_watch = "./hls"
    watcher = AsyncHLSFileWatcher(directory_to_watch)
    
    # Run the event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(watcher.run())
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        loop.close()
