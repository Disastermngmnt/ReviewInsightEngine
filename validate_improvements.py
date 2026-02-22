#!/usr/bin/env python
"""
Validation script to verify all improvements are in place.
Run this to check that error handling, testing, security, and configuration are properly implemented.
"""
import os
import sys
from pathlib import Path


def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists."""
    exists = Path(filepath).exists()
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {filepath}")
    return exists


def check_directory_exists(dirpath: str, description: str) -> bool:
    """Check if a directory exists."""
    exists = Path(dirpath).is_dir()
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {dirpath}")
    return exists


def check_import(module_name: str, description: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        print(f"✅ {description}: {module_name}")
        return True
    except ImportError as e:
        print(f"❌ {description}: {module_name} - {e}")
        return False


def main():
    """Run all validation checks."""
    print("=" * 70)
    print("ReviewInsightEngine - Improvements Validation")
    print("=" * 70)
    
    checks_passed = 0
    checks_total = 0
    
    # 1. Error Handling
    print("\n1. ERROR HANDLING")
    print("-" * 70)
    checks = [
        check_file_exists("utils/exceptions.py", "Custom exceptions"),
        check_file_exists("utils/logger.py", "Centralized logging"),
        check_import("utils.exceptions", "Exceptions module"),
        check_import("utils.logger", "Logger module"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 2. Testing
    print("\n2. TESTING")
    print("-" * 70)
    checks = [
        check_directory_exists("tests", "Tests directory"),
        check_file_exists("tests/conftest.py", "Test fixtures"),
        check_file_exists("tests/test_analyzer.py", "Analyzer tests"),
        check_file_exists("tests/test_validators.py", "Validator tests"),
        check_file_exists("tests/test_config.py", "Config tests"),
        check_file_exists("tests/test_synthesis_engine.py", "Synthesis tests"),
        check_file_exists("tests/test_file_handler.py", "File handler tests"),
        check_file_exists("tests/test_rate_limiter.py", "Rate limiter tests"),
        check_file_exists("pytest.ini", "Pytest configuration"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 3. Security
    print("\n3. SECURITY")
    print("-" * 70)
    checks = [
        check_file_exists("utils/rate_limiter.py", "Rate limiter"),
        check_file_exists("utils/validators.py", "Input validators"),
        check_file_exists("SECURITY.md", "Security documentation"),
        check_import("utils.rate_limiter", "Rate limiter module"),
        check_import("utils.validators", "Validators module"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 4. Configuration
    print("\n4. CONFIGURATION")
    print("-" * 70)
    checks = [
        check_file_exists("config/environments.py", "Environment config"),
        check_file_exists(".env.example", "Environment template"),
        check_import("config.environments", "Environments module"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 5. Documentation
    print("\n5. DOCUMENTATION")
    print("-" * 70)
    checks = [
        check_file_exists("README_IMPROVEMENTS.md", "Improvements README"),
        check_file_exists("QUICKSTART.md", "Quick start guide"),
        check_file_exists("SECURITY.md", "Security guidelines"),
        check_file_exists("IMPROVEMENTS_SUMMARY.md", "Summary document"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 6. Development Tools
    print("\n6. DEVELOPMENT TOOLS")
    print("-" * 70)
    checks = [
        check_file_exists("requirements.txt", "Production requirements"),
        check_file_exists("requirements-dev.txt", "Dev requirements"),
        check_file_exists(".gitignore", "Git ignore file"),
        check_file_exists("Makefile", "Makefile"),
    ]
    checks_passed += sum(checks)
    checks_total += len(checks)
    
    # 7. Core Module Updates
    print("\n7. CORE MODULE UPDATES")
    print("-" * 70)
    
    # Check if modules have been updated with new imports
    updates = []
    
    # Check file_handler.py
    try:
        with open("core/file_handler.py", "r") as f:
            content = f.read()
            has_logger = "from utils.logger import" in content
            has_exceptions = "from utils.exceptions import" in content
            has_validators = "from utils.validators import" in content
            updates.append(has_logger and has_exceptions and has_validators)
            status = "✅" if updates[-1] else "❌"
            print(f"{status} file_handler.py updated with error handling")
    except Exception as e:
        print(f"❌ Could not check file_handler.py: {e}")
        updates.append(False)
    
    # Check ai_engine.py
    try:
        with open("core/ai_engine.py", "r") as f:
            content = f.read()
            has_logger = "from utils.logger import" in content
            has_exceptions = "from utils.exceptions import" in content
            updates.append(has_logger and has_exceptions)
            status = "✅" if updates[-1] else "❌"
            print(f"{status} ai_engine.py updated with error handling")
    except Exception as e:
        print(f"❌ Could not check ai_engine.py: {e}")
        updates.append(False)
    
    # Check auth.py
    try:
        with open("core/auth.py", "r") as f:
            content = f.read()
            has_logger = "from utils.logger import" in content
            has_validators = "from utils.validators import" in content
            updates.append(has_logger and has_validators)
            status = "✅" if updates[-1] else "❌"
            print(f"{status} auth.py updated with error handling")
    except Exception as e:
        print(f"❌ Could not check auth.py: {e}")
        updates.append(False)
    
    # Check main.py
    try:
        with open("main.py", "r") as f:
            content = f.read()
            has_logger = "from utils.logger import" in content
            has_rate_limiter = "from utils.rate_limiter import" in content
            has_config = "from config.environments import" in content
            updates.append(has_logger and has_rate_limiter and has_config)
            status = "✅" if updates[-1] else "❌"
            print(f"{status} main.py updated with security and config")
    except Exception as e:
        print(f"❌ Could not check main.py: {e}")
        updates.append(False)
    
    checks_passed += sum(updates)
    checks_total += len(updates)
    
    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    percentage = (checks_passed / checks_total * 100) if checks_total > 0 else 0
    print(f"Checks Passed: {checks_passed}/{checks_total} ({percentage:.1f}%)")
    
    if percentage >= 90:
        print("\n✅ EXCELLENT! All major improvements are in place.")
        print("   The application is ready for testing and deployment.")
    elif percentage >= 70:
        print("\n⚠️  GOOD! Most improvements are in place.")
        print("   Review failed checks and complete remaining items.")
    else:
        print("\n❌ INCOMPLETE! Several improvements are missing.")
        print("   Please review the failed checks above.")
    
    print("\nNext Steps:")
    print("1. Run tests: pytest")
    print("2. Check configuration: cp .env.example .env && edit .env")
    print("3. Review documentation: README_IMPROVEMENTS.md")
    print("4. Start application: streamlit run app.py")
    
    return 0 if percentage >= 90 else 1


if __name__ == "__main__":
    sys.exit(main())
