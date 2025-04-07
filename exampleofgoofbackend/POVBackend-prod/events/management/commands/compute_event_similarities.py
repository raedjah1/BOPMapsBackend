from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from events.models import Event, EventSimilarity
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging
import pickle
from annoy import AnnoyIndex
import tempfile
import os
import time

logger = logging.getLogger(__name__)
CACHE_PREFIX = "event_similarity_"

class Command(BaseCommand):
    help = "Compute and update event similarities for recommendations"

    def handle(self, *args, **options):
        try:
            start_time = time.time()
            self.stdout.write("Starting event similarity computation...")
            
            # Get all upcoming events with their related data
            now = timezone.now()
            logger.info(f"Fetching upcoming events at {now.isoformat()}")
            events = list(Event.objects.select_related(
                'creator',
                'vision'
            ).prefetch_related(
                'vision__interests',
                'remind_me_list'
            ).filter(
                start_time__gte=now  # Only process upcoming events
            ))
            
            if not events:
                logger.info("No upcoming events found to process.")
                self.stdout.write("No upcoming events found to process.")
                return
            
            logger.info(f"Processing {len(events)} upcoming events")
            self.stdout.write(f"Processing {len(events)} upcoming events")
            
            # Add this to enhance the feature extraction and similarity calculation
            event_data = []
            logger.info("Building event feature data...")
            self.stdout.write("Building event feature data...")
            
            for event in events:
                # Get creator information
                creator_username = event.creator.user.username
                
                # Get interests from the associated vision
                interests = []
                if event.vision and event.vision.interests.exists():
                    interests = [interest.name for interest in event.vision.interests.all()]
                
                # More weight to the title and interests
                weighted_title = ' '.join([event.title] * 3)  # Triple the title
                weighted_interests = ' '.join(interests * 2)  # Double the interests
                
                # Combine all text with appropriate weights
                text = f"{weighted_title} {event.description} {weighted_interests} {creator_username}"
                
                event_data.append({
                    'event': event,
                    'text': text,
                    'interests': interests,
                    'creator': creator_username,
                    'remind_me_count': event.remind_me_list.count(),
                    'subscriber_count': event.creator.subscriber_count or 1
                })
            
            # Create text corpus
            self.stdout.write("Creating text corpus for TF-IDF vectorization...")
            event_texts = [data['text'] for data in event_data]
            
            # Add a better TF-IDF vectorizer
            logger.info("Initializing TF-IDF vectorizer with enhanced parameters")
            vectorizer = TfidfVectorizer(
                stop_words='english',
                max_features=1000,
                ngram_range=(1, 2),
                min_df=1,  # Accept terms that appear in at least 1 document
                max_df=1.0  # Don't filter out terms based on document frequency
            )
            
            # Transform texts to TF-IDF matrix
            self.stdout.write("Transforming event texts to TF-IDF matrix...")
            start_tfidf = time.time()
            tfidf_matrix = vectorizer.fit_transform(event_texts)
            logger.info(f"TF-IDF vectorization completed in {time.time() - start_tfidf:.2f} seconds. Matrix shape: {tfidf_matrix.shape}")
            
            # Handle edge case with too few events
            if len(events) < 2:
                logger.info("Not enough events to compute meaningful similarities.")
                self.stdout.write("Not enough events to compute meaningful similarities.")
                return
            
            # Compute similarity matrix
            self.stdout.write("Computing cosine similarity matrix...")
            start_similarity = time.time()
            similarity_matrix = cosine_similarity(tfidf_matrix)
            logger.info(f"Similarity matrix computation completed in {time.time() - start_similarity:.2f} seconds. Matrix shape: {similarity_matrix.shape}")
            
            # Create Annoy index for fast lookups
            self.stdout.write("Building ANN index with Annoy for events...")
            logger.info("Starting Annoy index construction for approximate nearest neighbors")
            start_annoy = time.time()
            
            # Get vector dimensionality
            vector_size = tfidf_matrix[0].shape[1]
            logger.info(f"Vector size for Annoy index: {vector_size}")
            
            # Create Annoy index
            annoy_index = AnnoyIndex(vector_size, 'angular')
            for i, event in enumerate(events):
                # Get dense vector representation
                vector = tfidf_matrix[i].toarray()[0]
                annoy_index.add_item(i, vector)
            
            # Build the index
            self.stdout.write(f"Adding {len(events)} events to Annoy index...")
            logger.info(f"Building Annoy index with {len(events)} events and 10 trees")
            annoy_index.build(10)  # 10 trees for good accuracy/speed tradeoff
            logger.info(f"Annoy index built in {time.time() - start_annoy:.2f} seconds")
            
            # Save to temporary file
            self.stdout.write("Saving Annoy index to temporary file...")
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            annoy_index.save(temp_file.name)
            logger.info(f"Annoy index saved to temporary file: {temp_file.name}")
            self.stdout.write("Annoy index built and saved to temporary file")
            
            # Read file bytes
            with open(temp_file.name, 'rb') as f:
                index_binary = f.read()
            
            # Clean up
            os.unlink(temp_file.name)
            logger.info(f"Temporary file removed after reading binary data ({len(index_binary)} bytes)")
            self.stdout.write("Read index binary data for database storage")
            
            # Start a transaction for bulk updates
            logger.info("Starting database transaction for bulk updates...")
            self.stdout.write("Starting database transaction for bulk updates...")
            start_db = time.time()
            
            with transaction.atomic():
                # Mark all existing as not current
                from events.models import EventAnnoyIndex
                prev_indices = EventAnnoyIndex.objects.filter(is_current=True).count()
                EventAnnoyIndex.objects.filter(is_current=True).update(is_current=False)
                logger.info(f"Marked {prev_indices} existing index(es) as not current")
                
                # Create new index
                index = EventAnnoyIndex.objects.create(
                    index_binary=index_binary,
                    event_ids=[e.id for e in events],
                    vector_size=vector_size,
                    is_current=True
                )
                logger.info(f"Created new Annoy index in database with ID: {index.id}")
                self.stdout.write(f"Annoy ANN index built and stored in DB (id: {index.id}) with {len(events)} events")
                
                # Clear existing similarities
                similarity_count = EventSimilarity.objects.count()
                EventSimilarity.objects.all().delete()
                logger.info(f"Deleted {similarity_count} existing similarity records")
                
                # Create new similarity entries
                similarities = []
                self.stdout.write("Calculating event similarities and updating event scores...")
                
                for i, event in enumerate(events):
                    # Store feature vector for future use
                    event.feature_vector = pickle.dumps(tfidf_matrix[i].toarray())
                    
                    # Update engagement and popularity scores
                    event.engagement_score = event.remind_me_list.count() / max(1, event.creator.subscriber_count)
                    
                    # Time-weighted popularity score
                    time_until_event = (event.start_time - now).total_seconds() / 86400  # Convert to days
                    event.popularity_score = event.remind_me_list.count() / (1 + time_until_event)
                    
                    event.last_recommendation_update = now
                    event.save()
                    
                    # Get indices of top similar events (excluding self)
                    similar_scores = similarity_matrix[i]
                    # Convert to regular Python integers and exclude self
                    similar_indices = [
                        int(idx) for idx in np.argsort(similar_scores)[::-1]
                        if idx != i
                    ][:10]  # Top 10 similar events
                    
                    for idx in similar_indices:
                        similar_event = events[idx]
                        similarity_score = float(similarity_matrix[i][idx])  # Convert to Python float
                        
                        # Calculate engagement boost based on similar event's performance
                        engagement_boost = similar_event.engagement_score * 0.5
                        
                        # Combine scores for final similarity
                        final_score = similarity_score + engagement_boost
                        
                        similarities.append(EventSimilarity(
                            event=event,
                            similar_event=similar_event,
                            similarity_score=similarity_score,
                            engagement_boost=engagement_boost,
                            final_score=final_score
                        ))
                
                # Bulk create similarities in batches
                batch_size = 1000
                total_similarities = len(similarities)
                logger.info(f"Preparing to create {total_similarities} similarity records in batches of {batch_size}")
                
                for i in range(0, len(similarities), batch_size):
                    batch = similarities[i:i + batch_size]
                    EventSimilarity.objects.bulk_create(batch)
                    logger.info(f"Created batch {i//batch_size + 1} with {len(batch)} similarity records")
            
            logger.info(f"Database transaction completed in {time.time() - start_db:.2f} seconds")
            total_time = time.time() - start_time
            logger.info(f"Total similarity computation completed in {total_time:.2f} seconds")
            
            self.stdout.write(self.style.SUCCESS(
                f"Successfully computed similarities for {len(events)} events in {total_time:.2f} seconds"
            ))
            
        except Exception as e:
            logger.error(f"Error computing event similarities: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}")) 