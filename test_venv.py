#!/usr/bin/env python3
"""
Simple test script to verify the virtual environment is working correctly.
"""
import sys
import os

def main():
    print("=== Virtual Environment Test ===")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Virtual environment: {os.environ.get('VIRTUAL_ENV', 'Not set')}")
    
    # Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Running in virtual environment")
    else:
        print("❌ NOT running in virtual environment")
    
    # Test importing a package that should be installed
    try:
        import requests
        print(f"✅ requests package available: {requests.__version__}")
    except ImportError:
        print("❌ requests package not available")
    
    try:
        import streamlink
        print(f"✅ streamlink package available: {streamlink.__version__}")
    except ImportError:
        print("❌ streamlink package not available")

if __name__ == "__main__":
    main()