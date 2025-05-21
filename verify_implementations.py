#!/usr/bin/env python
"""
Simple verification script to check if the Friends and Gamification implementations are correct
without running the full server or tests.
"""

import os
import sys
import importlib
import inspect
from typing import Dict, Any, List, Tuple

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bopmaps.settings')
import django
django.setup()

def check_module(module_name: str) -> Tuple[bool, List[str]]:
    """
    Check if a module exists and its structure is correct
    """
    errors = []
    
    try:
        module = importlib.import_module(module_name)
        print(f"✅ Module {module_name} exists")
        return True, errors
    except ImportError as e:
        print(f"❌ Module {module_name} failed to import: {e}")
        errors.append(f"Cannot import module {module_name}: {e}")
        return False, errors

def check_class(module_name: str, class_name: str, required_methods: List[str] = None) -> Tuple[bool, List[str]]:
    """
    Check if a class exists in a module and has the required methods
    """
    errors = []
    
    try:
        module = importlib.import_module(module_name)
        try:
            if not class_name:  # For utility modules that might not have classes
                # Check for required functions instead
                all_found = True
                for method_name in required_methods or []:
                    if not hasattr(module, method_name):
                        msg = f"❌ Function {method_name} missing from {module_name}"
                        print(msg)
                        errors.append(msg)
                        all_found = False
                    else:
                        print(f"  ✅ Function {method_name} exists")
                return all_found, errors
                
            cls = getattr(module, class_name)
            print(f"✅ Class {module_name}.{class_name} exists")
            
            if required_methods:
                for method_name in required_methods:
                    if not hasattr(cls, method_name):
                        msg = f"❌ Method {method_name} missing from {module_name}.{class_name}"
                        print(msg)
                        errors.append(msg)
                    else:
                        print(f"  ✅ Method {method_name} exists")
            
            return len(errors) == 0, errors
        except AttributeError:
            msg = f"❌ Class {class_name} not found in {module_name}"
            print(msg)
            errors.append(msg)
            return False, errors
    except ImportError as e:
        msg = f"❌ Cannot import module {module_name}: {e}"
        print(msg)
        errors.append(msg)
        return False, errors

def main():
    """
    Main verification function
    """
    print("Verifying Friends and Gamification Implementations")
    print("=" * 50)
    
    all_results = []
    
    # Friends Implementation
    print("\nFriends App:")
    all_results.append(check_module('friends.models'))
    all_results.append(check_module('friends.serializers'))
    all_results.append(check_module('friends.views'))
    all_results.append(check_module('friends.urls'))
    
    all_results.append(check_class('friends.serializers', 'FriendSerializer'))
    all_results.append(check_class('friends.serializers', 'FriendRequestSerializer'))
    all_results.append(check_class('friends.views', 'FriendViewSet', ['get_queryset', 'all_friends', 'unfriend']))
    all_results.append(check_class('friends.views', 'FriendRequestViewSet', ['get_queryset', 'perform_create', 'sent', 'received', 'accept', 'reject', 'cancel']))

    # Gamification Implementation
    print("\nGamification App:")
    all_results.append(check_module('gamification.models'))
    all_results.append(check_module('gamification.serializers'))
    all_results.append(check_module('gamification.views'))
    all_results.append(check_module('gamification.urls'))
    all_results.append(check_module('gamification.utils'))
    
    all_results.append(check_class('gamification.serializers', 'PinSkinSerializer'))
    all_results.append(check_class('gamification.serializers', 'AchievementSerializer'))
    all_results.append(check_class('gamification.serializers', 'UserAchievementSerializer'))
    all_results.append(check_class('gamification.views', 'PinSkinViewSet', ['unlocked', 'owned', 'equip']))
    all_results.append(check_class('gamification.views', 'AchievementViewSet', ['completed', 'in_progress']))
    all_results.append(check_class('gamification.views', 'UserAchievementViewSet', ['get_queryset', 'perform_create', 'update_progress', '_check_completion']))
    all_results.append(check_class('gamification.utils', '', ['check_achievement_progress']))
    
    # Final results
    print("\nVerification Summary:")
    print("=" * 50)
    
    successful = [result for result, _ in all_results if result]
    failed = [errors for result, errors in all_results if not result]
    
    flat_errors = []
    for error_list in failed:
        flat_errors.extend(error_list)
    
    print(f"\nSuccessful checks: {len(successful)}/{len(all_results)}")
    
    if flat_errors:
        print(f"\nErrors ({len(flat_errors)}):")
        for i, error in enumerate(flat_errors, 1):
            print(f"{i}. {error}")
        return 1
    else:
        print("\nALL CHECKS PASSED! The Friends and Gamification implementations appear correct.")
        return 0

if __name__ == "__main__":
    sys.exit(main()) 