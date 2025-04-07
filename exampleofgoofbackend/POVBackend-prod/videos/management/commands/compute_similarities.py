from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from videos.models import Vision, VisionSimilarity, AnnoyIndex
from users.models import WatchHistory, Interest
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import numpy as np
import logging
import pickle

# Replace nmslib with annoy
from annoy import AnnoyIndex
from scipy.sparse import coo_matrix, csr_matrix
import implicit

logger = logging.getLogger(__name__)

CACHE_PREFIX = "vision_similarity_"
CACHE_TIMEOUT = 60 * 60  # 1 hour

class Command(BaseCommand):
    help = "Compute vision similarities using vectorized operations, matrix factorization and ANN"

    def handle(self, *args, **options):
        try:
            self.stdout.write("Starting similarity computation...")
            
            # Get all interests and visions in one query
            all_interests = list(Interest.objects.values_list('name', flat=True))
            interest_to_idx = {name: idx for idx, name in enumerate(all_interests)}
            
            visions = list(Vision.objects.select_related(
                'creator'
            ).prefetch_related(
                'interests'
            ).filter(
                status__in=['vod', 'live']
            ))
            
            if not visions:
                self.stdout.write("No visions found to process.")
                return
            
            # Create efficient lookups
            vision_to_idx = {vision.id: idx for idx, vision in enumerate(visions)}
            
            # Process watch history in batches efficiently
            watch_patterns = self.get_watch_patterns(vision_to_idx)
            co_watch_matrix = self.compute_co_watch_matrix(watch_patterns, visions, vision_to_idx)
            
            # Compute feature matrix efficiently 
            feature_matrix = self.compute_feature_matrix(visions, all_interests, co_watch_matrix, interest_to_idx)
            
            # Enhance with matrix factorization
            als_factors = self.compute_als_factors(visions, vision_to_idx)
            
            # Combine both approaches - hybrid model
            combined_factors = np.hstack([
                self.normalize_features(feature_matrix) * 0.7,  # 70% weight to content/engagement
                als_factors * 0.3                              # 30% weight to matrix factorization
            ])
            
            # Use the combined factors for similarity calculation
            similarity_matrix = self.compute_similarity_matrix(combined_factors, visions)
            
            # Build and cache ANN index using Annoy instead of nmslib
            self.build_and_cache_ann_index(combined_factors, visions)
            
            # Update database
            self.update_database(visions, combined_factors, similarity_matrix)
            
            self.stdout.write(self.style.SUCCESS(
                f"Successfully computed similarities for {len(visions)} visions using matrix factorization"
            ))
            
        except Exception as e:
            logger.error(f"Error computing similarities: {e}")
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))

    def get_watch_patterns(self, vision_to_idx, batch_size=10000):
        watch_patterns = defaultdict(dict)
        now = timezone.now()
        max_days = 30
        offset = 0
        
        while True:
            watches = WatchHistory.objects.select_related(
                'user'
            ).order_by(
                '-watched_at'
            )[offset:offset + batch_size]
            
            batch = list(watches)
            if not batch:
                break
                
            for watch in batch:
                if watch.vision_id in vision_to_idx:
                    days_old = (now - watch.watched_at).days
                    recency_weight = max(0, (max_days - min(days_old, max_days)) / max_days)
                    watch_patterns[watch.user_id][watch.vision_id] = (watch.watched_at, recency_weight)
            
            offset += batch_size
            self.stdout.write(f"Processed {offset} watch history records...")
            
        return watch_patterns

    def compute_co_watch_matrix(self, watch_patterns, visions, vision_to_idx):
        n_visions = len(visions)
        co_watch_matrix = np.zeros((n_visions, n_visions), dtype=np.float32)
        
        for user_watches in watch_patterns.values():
            sorted_watches = sorted(user_watches.items(), key=lambda x: x[1][0], reverse=True)
            for i, (vid1, (_, weight1)) in enumerate(sorted_watches):
                for j, (vid2, (_, weight2)) in enumerate(sorted_watches[i+1:], i+1):
                    idx1, idx2 = vision_to_idx[vid1], vision_to_idx[vid2]
                    score = (weight1 + weight2) / 2
                    co_watch_matrix[idx1][idx2] += score
                    co_watch_matrix[idx2][idx1] += score
        
        return co_watch_matrix

    def compute_feature_matrix(self, visions, all_interests, co_watch_matrix, interest_to_idx):
        n_visions = len(visions)
        n_features = 7 + len(all_interests)  # engagement metrics + interests
        feature_matrix = np.zeros((n_visions, n_features), dtype=np.float32)
        
        now = timezone.now()
        max_days = 30
        
        for i, vision in enumerate(visions):
            # Engagement features
            days_old = max((now - vision.created_at).days, 0)
            time_factor = max(0, (max_days - min(days_old, max_days)) / max_days)
            
            engagement = (vision.likes + vision.comment_count) / max(vision.views, 1)
            popularity = (vision.views + vision.likes * 2 + vision.comment_count * 3) * time_factor
            
            # Basic features
            feature_matrix[i, 0] = engagement * (1 + time_factor)
            feature_matrix[i, 1] = popularity
            feature_matrix[i, 2] = vision.likes
            feature_matrix[i, 3] = vision.views
            feature_matrix[i, 4] = vision.comment_count
            feature_matrix[i, 5] = np.sum(co_watch_matrix[i]) / n_visions
            feature_matrix[i, 6] = time_factor
            
            # Interest features
            vision_interests = set(vision.interests.values_list('name', flat=True))
            for interest_name, idx in interest_to_idx.items():
                feature_matrix[i, 7 + idx] = 1.0 if interest_name in vision_interests else 0.0
        
        return feature_matrix

    def normalize_features(self, feature_matrix):
        engagement_features = feature_matrix[:, :7]
        interest_features = feature_matrix[:, 7:]
        
        scaler_engagement = MinMaxScaler()
        scaler_interest = MinMaxScaler()
        
        normalized_engagement = scaler_engagement.fit_transform(engagement_features)
        normalized_interests = scaler_interest.fit_transform(interest_features) if interest_features.shape[1] > 0 else np.array([])
        
        if normalized_interests.size > 0:
            return np.hstack([
                normalized_engagement * 0.7,  # 70% weight
                normalized_interests * 0.3    # 30% weight
            ])
        return normalized_engagement

    def compute_similarity_matrix(self, normalized_features, visions):
        # Compute base similarity using vectorized cosine similarity
        base_similarity = cosine_similarity(normalized_features)
        
        # Add small epsilon to avoid division by zero
        base_similarity += 1e-10
        
        # Ensure diagonal is zero (no self-similarity)
        np.fill_diagonal(base_similarity, 0)
        
        return base_similarity

    def update_database(self, visions, normalized_features, similarity_matrix):
        now = timezone.now()
        
        with transaction.atomic():
            # Update vision scores
            vision_updates = []
            for i, vision in enumerate(visions):
                vision.engagement_score = float(max(0.0, normalized_features[i][0]))
                vision.popularity_score = float(max(0.0, normalized_features[i][1]))
                vision.last_recommendation_update = now
                vision_updates.append(vision)
            
            Vision.objects.bulk_update(
                vision_updates,
                ['engagement_score', 'popularity_score', 'last_recommendation_update'],
                batch_size=1000
            )

            # More efficient similarity update - avoid duplicates by using vision pairs as keys
            similarity_dict = {}  # Use vision pair as key to avoid duplicates
            
            for i, vision_i in enumerate(visions):
                # Get top 10 similar visions
                similar_indices = np.argsort(similarity_matrix[i])[::-1][:10]
                
                for idx in similar_indices:
                    if idx != i:
                        # Create an ordered key pair to ensure uniqueness
                        vision_pair = (min(vision_i.pk, visions[idx].pk), max(vision_i.pk, visions[idx].pk))
                        
                        similarity_score = float(similarity_matrix[i][idx])
                        engagement_boost = float(normalized_features[idx][0]) * 0.5
                        recency_boost = float(normalized_features[idx][6]) * 0.2
                        final_score = max(0.0, min(1.0, similarity_score + engagement_boost + recency_boost))
                        
                        # Only keep the highest score for each pair
                        if vision_pair not in similarity_dict or similarity_dict[vision_pair][4] < final_score:
                            similarity_dict[vision_pair] = (
                                vision_i,
                                visions[idx],
                                similarity_score,
                                engagement_boost + recency_boost,
                                final_score
                            )
            
            # Clear existing similarities and bulk create new ones
            VisionSimilarity.objects.all().delete()
            
            similarities = [
                VisionSimilarity(
                    vision=data[0],
                    similar_vision=data[1],
                    similarity_score=data[2],
                    engagement_boost=data[3],
                    final_score=data[4]
                )
                for data in similarity_dict.values()
            ]
            
            # Bulk create similarities in batches
            VisionSimilarity.objects.bulk_create(similarities, batch_size=1000)
            
            # Cache the results
            cache.set(
                f"{CACHE_PREFIX}last_update",
                now,
                CACHE_TIMEOUT
            ) 

    def compute_als_factors(self, visions, vision_to_idx):
        """
        Compute Alternating Least Squares factorization for vision similarity.
        Uses implicit feedback (views, watch time, likes) to build a user-item matrix.
        """
        try:
            self.stdout.write("Computing ALS factors...")
            
            # Get all user-vision interactions
            user_vision_matrix = self.build_user_vision_matrix(visions, vision_to_idx)
            
            if user_vision_matrix is None or user_vision_matrix.nnz == 0:
                self.stdout.write("Insufficient data for ALS. Using fallback.")
                return np.random.rand(len(visions), 50)  # Fallback
            
            # Initialize and train ALS model
            model = implicit.als.AlternatingLeastSquares(
                factors=50,          # Number of latent factors
                regularization=0.1,  # Regularization factor 
                iterations=15,       # Number of iterations
                calculate_training_loss=True
            )
            
            # Train the model
            model.fit(user_vision_matrix)
            
            # Get the item factors (vision embeddings)
            vision_factors = model.item_factors
            
            self.stdout.write(f"ALS model trained successfully with {vision_factors.shape[1]} factors")
            return vision_factors
            
        except Exception as e:
            logger.error(f"Error computing ALS factors: {e}")
            # Fallback to random factors if computation fails
            self.stdout.write(self.style.WARNING(f"Using random factors due to error: {e}"))
            return np.random.rand(len(visions), 50)
    
    def build_user_vision_matrix(self, visions, vision_to_idx):
        """
        Build a sparse matrix of user-vision interactions
        with appropriate weighting for different signals.
        """
        try:
            # Get all watch history data efficiently
            watch_histories = WatchHistory.objects.values('user_id', 'vision_id', 'watched_at')
            
            # Extract unique users
            unique_users = set(wh['user_id'] for wh in watch_histories)
            if not unique_users:
                return None
                
            user_to_idx = {user_id: idx for idx, user_id in enumerate(unique_users)}
            
            # Build sparse interaction matrix
            rows, cols, data = [], [], []
            now = timezone.now()
            
            # Add watch history interactions
            for wh in watch_histories:
                if wh['vision_id'] in vision_to_idx:
                    user_idx = user_to_idx[wh['user_id']]
                    vision_idx = vision_to_idx[wh['vision_id']]
                    
                    # Use recency-weighted confidence
                    watched_at = wh['watched_at']
                    days_old = (now - watched_at).days if watched_at else 30
                    recency_weight = max(0.1, 1.0 - (days_old / 30.0))  # Higher weight for recent watches
                    
                    rows.append(user_idx)
                    cols.append(vision_idx)
                    data.append(recency_weight)
            
            # Add stronger signals for high engagement
            for vision in visions:
                idx = vision_to_idx[vision.id]
                engagement = (vision.likes + vision.comment_count) / max(vision.views, 1)
                
                # Add synthetic interactions for highly engaged content
                if engagement > 0.2:  # Only for content with significant engagement
                    boost_factor = min(5.0, engagement * 10)  # Cap at 5x
                    
                    # Add boosted interactions for estimated engaged users
                    est_engaged_users = min(len(unique_users) // 10, 
                                           int(vision.views * engagement))
                    
                    for i in range(min(est_engaged_users, 100)):  # Limit to 100 synthetic interactions
                        user_idx = i % len(user_to_idx)
                        rows.append(user_idx)
                        cols.append(idx)
                        data.append(boost_factor)
            
            # Create sparse matrix
            user_vision_matrix = coo_matrix(
                (data, (rows, cols)), 
                shape=(len(unique_users), len(visions)),
                dtype=np.float32
            )
            
            # Convert to CSR format for efficient operations
            self.stdout.write(f"Built user-vision matrix with {user_vision_matrix.nnz} non-zero entries")
            return user_vision_matrix.tocsr()
            
        except Exception as e:
            logger.error(f"Error building user-vision matrix: {e}")
            return None

    def build_and_cache_ann_index(self, combined_factors, visions):
        """
        Build and store an Approximate Nearest Neighbor (ANN) index in the database
        using Annoy for better compatibility and persistence
        """
        try:
            self.stdout.write("Building ANN index with Annoy...")
            
            # Get dimensions of the factors
            vector_size = combined_factors.shape[1]
            
            # Initialize Annoy index with cosine distance (angular)
            index = AnnoyIndex(vector_size, 'angular')
            
            # Add vision vectors to the index
            for i, vision_vector in enumerate(combined_factors):
                index.add_item(i, vision_vector)
            
            # Build the index with 10 trees - more trees = more accuracy but slower build
            index.build(10)
            
            # Save the index to a temporary file
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            index_path = temp_file.name
            temp_file.close()
            
            index.save(index_path)
            
            # Load the file into memory and delete the temporary file
            with open(index_path, 'rb') as f:
                index_binary = f.read()
            
            import os
            os.unlink(index_path)
            
            # Mark all previous indexes as not current in a transaction
            with transaction.atomic():
                from videos.models import AnnoyIndex as AnnoyIndexModel
                AnnoyIndexModel.objects.filter(is_current=True).update(is_current=False)
                
                # Create new index entry
                vision_ids = [vision.id for vision in visions]
                ann_index = AnnoyIndexModel.objects.create(
                    index_binary=index_binary,
                    vector_size=vector_size,
                    is_current=True
                )
                ann_index.vision_ids = vision_ids  # Use the property setter
                ann_index.save()
            
            # Also cache for fast access
            cache_data = {
                'index_binary': bytes(index_binary),  # Convert to bytes if needed
                'vision_ids': vision_ids,
                'vector_size': vector_size,
                'last_update': timezone.now().isoformat(),
                'vision_count': len(visions)
            }
            cache.set(f"{CACHE_PREFIX}ann_index", cache_data, CACHE_TIMEOUT * 24)
            
            self.stdout.write(self.style.SUCCESS(
                f"Annoy ANN index built and stored in DB (id: {ann_index.id}) with {len(visions)} visions"
            ))
            return True
            
        except Exception as e:
            logger.error(f"Error building Annoy index: {e}")
            self.stdout.write(self.style.WARNING(f"ANN index could not be built: {e}"))
            return False 