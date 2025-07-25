#!/usr/bin/env python3
"""
RFMS PDF XTRACR - Setup Verification Script
This script verifies that all components are properly configured and working.
"""

import os
import sys
import importlib
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher."""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} - Requires Python 3.8+")
        return False

def check_required_files():
    """Check if all required files exist."""
    print("\n📁 Checking required files...")
    required_files = [
        'app.py',
        'requirements.txt',
        'mapping.md',
        'SETUP_GUIDE.md',
        'utils/payload_service.py',
        'utils/rfms_api.py',
        'utils/pdf_extractor.py',
        'models/__init__.py',
        'models/customer.py',
        'models/pdf_data.py',
        'models/job.py',
        'models/quote.py',
        'models/rfms_session.py'
    ]
    
    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - Missing")
            all_exist = False
    
    return all_exist

def check_directories():
    """Check if required directories exist."""
    print("\n📂 Checking required directories...")
    required_dirs = [
        'utils',
        'models',
        'templates',
        'static',
        'uploads',
        'themes'
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"   ✅ {dir_path}/")
        else:
            print(f"   ❌ {dir_path}/ - Missing")
            all_exist = False
    
    return all_exist

def main():
    """Run all verification checks."""
    print("🔍 RFMS PDF XTRACR - Setup Verification")
    print("=" * 50)
    
    checks = [
        ("Python Version", check_python_version),
        ("Required Files", check_required_files),
        ("Directories", check_directories)
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"   ❌ Error during {check_name} check: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {check_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 Setup verification completed successfully!")
        print("💡 Next steps:")
        print("   1. Configure your .env file with RFMS API credentials")
        print("   2. Run 'python init_db.py' to initialize the database")
        print("   3. Run 'python app.py' to start the application")
    else:
        print(f"\n⚠️  {total - passed} checks failed. Please review the issues above.")
        print("💡 Refer to SETUP_GUIDE.md for detailed setup instructions.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
 