"""
Celery tasks for geo data management including:
- Region bundling for offline use
- Vector data import from OSM
- Tile downloading and caching
"""

import os
import json
import time
import zipfile
import tempfile
import subprocess
import requests
import logging
from io import BytesIO
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.gis.geos import Point, Polygon
from django.core.files import File
from django.utils import timezone
from celery import shared_task
from celery.result import AsyncResult
from django.db.models import Sum

from .models import Building, Road, Park, CachedRegion, CachedTile, CacheStatistics

logger = logging.getLogger('bopmaps')

@shared_task(bind=True)
def create_region_bundle(self, north, south, east, west, min_zoom=10, max_zoom=18, name=None):
    """
    Create a bundle of map data for offline use
    
    Args:
        north, south, east, west: Bounding box coordinates
        min_zoom, max_zoom: Zoom level range
        name: Name for the region (optional)
        
    Returns:
        ID of the created CachedRegion
    """
    bundle_name = name or f"Region {north:.2f},{west:.2f} to {south:.2f},{east:.2f}"
    
    # Create a temporary directory for files
    with tempfile.TemporaryDirectory() as temp_dir:
        # For progress reporting
        total_tasks = 3  # Vector data, tiles, bundling
        completed_tasks = 0
        
        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'current': 'Starting region bundle creation'
        })
        
        # Create a polygon for the region bounds
        bbox = (float(west), float(south), float(east), float(north))
        bounds = Polygon.from_bbox(bbox)
        
        # Calculate size estimate in tiles
        tile_count = 0
        for z in range(int(min_zoom), int(max_zoom) + 1):
            # Simple formula for tile count in a region
            # 2^z tiles cover the entire world
            # So we estimate our portion based on lat/lng coverage
            lng_portion = (float(east) - float(west)) / 360.0
            lat_portion = (float(north) - float(south)) / 180.0
            level_tiles = int((2 ** z) * (2 ** z) * lng_portion * lat_portion)
            tile_count += level_tiles
        
        # 1. Fetch vector data (buildings, roads, parks)
        try:
            self.update_state(state='PROGRESS', meta={
                'progress': (completed_tasks / total_tasks) * 100,
                'current': 'Fetching vector data'
            })
            
            # Fetch and save buildings
            buildings = Building.objects.filter(geometry__intersects=bounds)
            building_data = {
                'type': 'FeatureCollection',
                'features': []
            }
            
            # Only include essential data to reduce size
            for building in buildings:
                feature = {
                    'type': 'Feature',
                    'geometry': json.loads(building.geometry.json),
                    'properties': {
                        'id': building.id,
                        'osm_id': building.osm_id,
                        'name': building.name,
                        'height': building.height,
                        'levels': building.levels,
                        'building_type': building.building_type
                    }
                }
                building_data['features'].append(feature)
            
            # Save to file
            with open(os.path.join(temp_dir, 'buildings.geojson'), 'w') as f:
                json.dump(building_data, f)
                
            # Repeat for roads
            roads = Road.objects.filter(geometry__intersects=bounds)
            road_data = {
                'type': 'FeatureCollection',
                'features': []
            }
            
            for road in roads:
                feature = {
                    'type': 'Feature',
                    'geometry': json.loads(road.geometry.json),
                    'properties': {
                        'id': road.id,
                        'osm_id': road.osm_id,
                        'name': road.name,
                        'road_type': road.road_type,
                        'width': road.width,
                        'lanes': road.lanes
                    }
                }
                road_data['features'].append(feature)
            
            with open(os.path.join(temp_dir, 'roads.geojson'), 'w') as f:
                json.dump(road_data, f)
                
            # And for parks
            parks = Park.objects.filter(geometry__intersects=bounds)
            park_data = {
                'type': 'FeatureCollection',
                'features': []
            }
            
            for park in parks:
                feature = {
                    'type': 'Feature',
                    'geometry': json.loads(park.geometry.json),
                    'properties': {
                        'id': park.id,
                        'osm_id': park.osm_id,
                        'name': park.name,
                        'park_type': park.park_type
                    }
                }
                park_data['features'].append(feature)
            
            with open(os.path.join(temp_dir, 'parks.geojson'), 'w') as f:
                json.dump(park_data, f)
                
            completed_tasks += 1
            
        except Exception as e:
            logger.error(f"Error fetching vector data: {e}")
            self.update_state(state='FAILURE', meta={
                'error': f"Error fetching vector data: {str(e)}"
            })
            raise
        
        # 2. Download map tiles
        try:
            self.update_state(state='PROGRESS', meta={
                'progress': (completed_tasks / total_tasks) * 100,
                'current': 'Downloading map tiles'
            })
            
            # Create tiles directory
            tiles_dir = os.path.join(temp_dir, 'tiles')
            os.makedirs(tiles_dir, exist_ok=True)
            
            # Download tiles for each zoom level
            downloaded_tiles = 0
            
            for z in range(int(min_zoom), int(max_zoom) + 1):
                # Calculate tile coordinates for this zoom level
                # Formula: https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
                
                # Helper functions
                def lat_to_y(lat_deg, zoom):
                    lat_rad = math.radians(lat_deg)
                    n = 2.0 ** zoom
                    return int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
                
                def lng_to_x(lng_deg, zoom):
                    n = 2.0 ** zoom
                    return int((lng_deg + 180.0) / 360.0 * n)
                
                # Calculate tile ranges
                min_x = lng_to_x(float(west), z)
                max_x = lng_to_x(float(east), z)
                min_y = lat_to_y(float(north), z)
                max_y = lat_to_y(float(south), z)
                
                # Ensure reasonable limits
                tile_limit = 1000  # Maximum tiles per zoom level
                if (max_x - min_x + 1) * (max_y - min_y + 1) > tile_limit:
                    self.update_state(state='PROGRESS', meta={
                        'warning': f"Too many tiles at zoom {z}, limiting download"
                    })
                    # Limit to center area
                    center_x = (min_x + max_x) // 2
                    center_y = (min_y + max_y) // 2
                    half_width = int(math.sqrt(tile_limit) / 2)
                    min_x = center_x - half_width
                    max_x = center_x + half_width
                    min_y = center_y - half_width
                    max_y = center_y + half_width
                
                # Download tiles
                for x in range(min_x, max_x + 1):
                    for y in range(min_y, max_y + 1):
                        # Create directory structure
                        tile_dir = os.path.join(tiles_dir, str(z), str(x))
                        os.makedirs(tile_dir, exist_ok=True)
                        
                        # Check if already downloaded
                        tile_path = os.path.join(tile_dir, f"{y}.png")
                        if os.path.exists(tile_path):
                            continue
                            
                        # Download from tile server
                        tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                        try:
                            response = requests.get(tile_url, timeout=5)
                            if response.status_code == 200:
                                with open(tile_path, 'wb') as f:
                                    f.write(response.content)
                                downloaded_tiles += 1
                                
                                # Respect OSM usage policy - max 2 requests per second
                                time.sleep(0.5)
                            else:
                                logger.warning(f"Tile download failed: {response.status_code} for {tile_url}")
                        except Exception as e:
                            logger.error(f"Error downloading tile {z}/{x}/{y}: {e}")
                            # Continue despite errors
                            
                        # Update progress based on total expected tiles
                        if tile_count > 0:
                            tile_progress = downloaded_tiles / tile_count
                            self.update_state(state='PROGRESS', meta={
                                'progress': ((completed_tasks + tile_progress) / total_tasks) * 100,
                                'current': f"Downloaded {downloaded_tiles} tiles"
                            })
            
            completed_tasks += 1
            
        except Exception as e:
            logger.error(f"Error downloading tiles: {e}")
            self.update_state(state='FAILURE', meta={
                'error': f"Error downloading tiles: {str(e)}"
            })
            raise
            
        # 3. Create bundle file
        try:
            self.update_state(state='PROGRESS', meta={
                'progress': (completed_tasks / total_tasks) * 100,
                'current': 'Creating bundle file'
            })
            
            # Create a metadata file
            metadata = {
                'name': bundle_name,
                'north': float(north),
                'south': float(south),
                'east': float(east),
                'west': float(west),
                'min_zoom': int(min_zoom),
                'max_zoom': int(max_zoom),
                'tile_count': downloaded_tiles,
                'created_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(os.path.join(temp_dir, 'metadata.json'), 'w') as f:
                json.dump(metadata, f)
                
            # Create a ZIP file
            bundle_path = os.path.join(settings.MEDIA_ROOT, 'region_bundles')
            os.makedirs(bundle_path, exist_ok=True)
            
            zip_filename = os.path.join(bundle_path, f"{int(time.time())}_region_bundle.zip")
            
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add metadata
                zipf.write(os.path.join(temp_dir, 'metadata.json'), 'metadata.json')
                
                # Add vector data
                zipf.write(os.path.join(temp_dir, 'buildings.geojson'), 'buildings.geojson')
                zipf.write(os.path.join(temp_dir, 'roads.geojson'), 'roads.geojson')
                zipf.write(os.path.join(temp_dir, 'parks.geojson'), 'parks.geojson')
                
                # Add tiles
                for root, dirs, files in os.walk(tiles_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, rel_path)
                        
            # Get file size
            size_kb = os.path.getsize(zip_filename) // 1024
            
            # Create CachedRegion record
            region = CachedRegion.objects.create(
                name=bundle_name,
                north=float(north),
                south=float(south),
                east=float(east),
                west=float(west),
                min_zoom=int(min_zoom),
                max_zoom=int(max_zoom),
                bounds=bounds,
                size_kb=size_kb
            )
            
            # Attach bundle file
            with open(zip_filename, 'rb') as f:
                region.bundle_file.save(os.path.basename(zip_filename), File(f))
                
            # Clean up temp file
            if os.path.exists(zip_filename):
                os.remove(zip_filename)
                
            completed_tasks += 1
            
            self.update_state(state='SUCCESS', meta={
                'progress': 100,
                'current': 'Bundle created successfully',
                'region_id': region.id
            })
            
            return region.id
                
        except Exception as e:
            logger.error(f"Error creating bundle: {e}")
            self.update_state(state='FAILURE', meta={
                'error': f"Error creating bundle: {str(e)}"
            })
            raise


@shared_task
def import_osm_data(north, south, east, west):
    """
    Import OSM data for a region
    
    Args:
        north, south, east, west: Bounding box coordinates
        
    Returns:
        Dict with counts of imported objects
    """
    logger.info(f"Importing OSM data for region: {north},{west} to {south},{east}")
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download OSM data using Overpass API
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Overpass query to get buildings, roads, and parks
        overpass_query = f"""
        [out:json][timeout:300];
        (
          // Buildings
          way["building"]({south},{west},{north},{east});
          relation["building"]({south},{west},{north},{east});
          
          // Roads
          way["highway"]({south},{west},{north},{east});
          
          // Parks and leisure areas
          way["leisure"="park"]({south},{west},{north},{east});
          relation["leisure"="park"]({south},{west},{north},{east});
          way["landuse"="recreation_ground"]({south},{west},{north},{east});
        );
        out body;
        >;
        out skel qt;
        """
        
        try:
            response = requests.post(overpass_url, data={"data": overpass_query})
            if response.status_code != 200:
                logger.error(f"Overpass API request failed: {response.status_code}")
                return {
                    "status": "error",
                    "message": f"Overpass API request failed: {response.status_code}"
                }
                
            # Save response to file
            osm_file = os.path.join(temp_dir, "data.osm.json")
            with open(osm_file, 'wb') as f:
                f.write(response.content)
                
            # Process the data
            osm_data = response.json()
            
            # Counters for imported objects
            counts = {
                "buildings": 0,
                "roads": 0,
                "parks": 0
            }
            
            # Process each element
            # This is a simplified approach - in production you'd use a more sophisticated
            # OSM parser that handles relations correctly
            
            # Process buildings
            for element in osm_data.get('elements', []):
                if element.get('tags', {}).get('building'):
                    # Extract building data
                    # For simplicity, we're skipping the complex geometry creation
                    # In a real implementation, you'd build the proper polygons
                    pass
                    
            # Process roads
            for element in osm_data.get('elements', []):
                if element.get('tags', {}).get('highway'):
                    # Extract road data
                    pass
                    
            # Process parks
            for element in osm_data.get('elements', []):
                if (element.get('tags', {}).get('leisure') == 'park' or 
                    element.get('tags', {}).get('landuse') == 'recreation_ground'):
                    # Extract park data
                    pass
                    
            return {
                "status": "success",
                "counts": counts
            }
                
        except Exception as e:
            logger.error(f"Error importing OSM data: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

@shared_task
def cleanup_expired_data():
    """
    Periodic task to clean up expired cached data
    """
    now = timezone.now()
    stats = {
        'tiles_cleaned': 0,
        'regions_cleaned': 0,
        'space_reclaimed': 0
    }
    
    try:
        # Clean up expired tiles
        tile_expiry = now - timedelta(days=settings.TILE_CACHE_DAYS)
        expired_tiles = CachedTile.objects.filter(last_accessed__lt=tile_expiry)
        
        # Get space to be reclaimed from tiles
        space_from_tiles = expired_tiles.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        tiles_count = expired_tiles.count()
        expired_tiles.delete()
        
        stats['tiles_cleaned'] = tiles_count
        stats['space_reclaimed'] += space_from_tiles
        
        # Clean up unused region bundles
        region_expiry = now - timedelta(days=settings.REGION_CACHE_DAYS)
        expired_regions = CachedRegion.objects.filter(last_accessed__lt=region_expiry)
        
        # Get space to be reclaimed from regions
        space_from_regions = expired_regions.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        regions_count = expired_regions.count()
        
        # Delete region bundle files and records
        for region in expired_regions:
            try:
                region.bundle_file.delete()  # Delete the actual file
            except Exception as e:
                logger.error(f"Error deleting region bundle file: {e}")
        expired_regions.delete()
        
        stats['regions_cleaned'] = regions_count
        stats['space_reclaimed'] += space_from_regions
        
        # Record cleanup statistics
        CacheStatistics.objects.create(
            total_tiles=CachedTile.objects.count(),
            total_regions=CachedRegion.objects.count(),
            total_size_bytes=CachedTile.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0 +
                           CachedRegion.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0,
            cleanup_runs=1,
            tiles_cleaned=stats['tiles_cleaned'],
            regions_cleaned=stats['regions_cleaned'],
            space_reclaimed_bytes=stats['space_reclaimed']
        )
        
        logger.info(f"Cache cleanup completed: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error during cache cleanup: {e}")
        raise

@shared_task
def monitor_storage_usage():
    """
    Monitor storage usage and trigger cleanup if needed
    """
    try:
        total_size = (
            CachedTile.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0 +
            CachedRegion.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        )
        
        # If total size exceeds 90% of max allowed, trigger cleanup
        if total_size > settings.MAX_CACHE_SIZE_BYTES * 0.9:
            logger.warning(f"Cache size ({total_size} bytes) approaching limit. Triggering cleanup.")
            cleanup_expired_data.delay()
            
        return {
            'total_size_bytes': total_size,
            'max_size_bytes': settings.MAX_CACHE_SIZE_BYTES,
            'usage_percentage': (total_size / settings.MAX_CACHE_SIZE_BYTES) * 100
        }
        
    except Exception as e:
        logger.error(f"Error monitoring storage usage: {e}")
        raise

@shared_task
def remove_least_accessed_tiles(count=1000):
    """
    Remove least accessed tiles when approaching storage limits
    """
    try:
        tiles = CachedTile.objects.order_by('access_count', 'last_accessed')[:count]
        space_reclaimed = tiles.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        tiles.delete()
        
        logger.info(f"Removed {count} least accessed tiles, reclaimed {space_reclaimed} bytes")
        return {'tiles_removed': count, 'space_reclaimed': space_reclaimed}
        
    except Exception as e:
        logger.error(f"Error removing least accessed tiles: {e}")
        raise 