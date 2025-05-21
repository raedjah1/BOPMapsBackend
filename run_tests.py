#!/usr/bin/env python
"""
Test runner script for the BOPMaps project.
Runs all tests and generates coverage reports.
"""

import os
import sys
import argparse
import json
import subprocess
from datetime import datetime

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run BOPMaps tests')
    parser.add_argument('--app', help='Specific app to test (e.g., users, pins)')
    parser.add_argument('--test', help='Specific test to run (e.g., UserAuthTests.test_user_can_register)')
    parser.add_argument('--coverage', action='store_true', help='Generate coverage report')
    parser.add_argument('--html', action='store_true', help='Generate HTML coverage report')
    parser.add_argument('--verbosity', type=int, default=1, help='Verbosity level (0-3)')
    parser.add_argument('--keepdb', action='store_true', help='Preserve test database between runs')
    return parser.parse_args()

def run_tests(args):
    """Run the tests with the given arguments"""
    print("=" * 80)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"BOPMaps Test Runner - {current_time}")
    print("=" * 80)
    
    # Construct test command
    cmd = [sys.executable, 'manage.py', 'test']
    
    # Add specific app or test if specified
    if args.app:
        app_name = args.app
        cmd.append(app_name)
        if args.test:
            cmd[-1] += f".{args.test}"
    
    # Add verbosity
    cmd.extend(['--verbosity', str(args.verbosity)])
    
    # Add keepdb if specified
    if args.keepdb:
        cmd.append('--keepdb')
    
    # Set the test settings module
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bopmaps.test_settings'
    
    # If coverage enabled, wrap with coverage command
    if args.coverage:
        cmd = [
            'coverage', 'run', 
            '--source=.', 
            '--omit=*/migrations/*,*/venv/*,*/venv_py311/*,*/tests/*',
        ] + cmd
    
    # Run the tests
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 80)
    result = subprocess.run(cmd)
    
    # Generate coverage report if requested
    if args.coverage and result.returncode == 0:
        print("\n" + "=" * 80)
        print("COVERAGE REPORT")
        print("=" * 80)
        
        # Text report
        subprocess.run(['coverage', 'report'])
        
        # HTML report if requested
        if args.html:
            subprocess.run(['coverage', 'html'])
            print("\nHTML coverage report generated in htmlcov/ directory")
            print("Open htmlcov/index.html in your browser to view")
    
    return result.returncode

def main():
    """Main function"""
    args = parse_args()
    sys.exit(run_tests(args))

if __name__ == '__main__':
    main() 