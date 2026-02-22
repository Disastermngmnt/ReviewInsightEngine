"""
Tests for input validation utilities.
"""
import pytest
from utils.validators import (
    validate_file_extension,
    validate_file_size,
    validate_order_id,
    validate_dataframe_structure,
    sanitize_text_input
)
from utils.exceptions import ValidationError


class TestFileValidation:
    def test_valid_csv_extension(self):
        validate_file_extension("data.csv", [".csv", ".xlsx"])
        # Should not raise
    
    def test_valid_xlsx_extension(self):
        validate_file_extension("data.xlsx", [".csv", ".xlsx"])
        # Should not raise
    
    def test_invalid_extension(self):
        with pytest.raises(ValidationError) as exc:
            validate_file_extension("data.txt", [".csv", ".xlsx"])
        assert "not allowed" in str(exc.value)
    
    def test_empty_filename(self):
        with pytest.raises(ValidationError):
            validate_file_extension("", [".csv"])
    
    def test_case_insensitive_extension(self):
        validate_file_extension("DATA.CSV", [".csv"])
        # Should not raise


class TestFileSizeValidation:
    def test_valid_file_size(self):
        validate_file_size(1024 * 1024, 50)  # 1MB, max 50MB
        # Should not raise
    
    def test_file_too_large(self):
        with pytest.raises(ValidationError) as exc:
            validate_file_size(100 * 1024 * 1024, 50)  # 100MB, max 50MB
        assert "exceeds maximum" in str(exc.value)
    
    def test_exact_max_size(self):
        max_mb = 10
        exact_bytes = max_mb * 1024 * 1024
        validate_file_size(exact_bytes, max_mb)
        # Should not raise


class TestOrderIdValidation:
    def test_valid_order_id(self):
        result = validate_order_id("ORD-123")
        assert result == "ORD-123"
    
    def test_lowercase_normalized(self):
        result = validate_order_id("ord-456")
        assert result == "ORD-456"
    
    def test_whitespace_trimmed(self):
        result = validate_order_id("  TEST123  ")
        assert result == "TEST123"
    
    def test_empty_order_id(self):
        with pytest.raises(ValidationError):
            validate_order_id("")
    
    def test_whitespace_only(self):
        with pytest.raises(ValidationError):
            validate_order_id("   ")
    
    def test_invalid_characters(self):
        with pytest.raises(ValidationError) as exc:
            validate_order_id("ORD@123!")
        assert "invalid characters" in str(exc.value)
    
    def test_too_short(self):
        with pytest.raises(ValidationError) as exc:
            validate_order_id("AB")
        assert "between 3 and 50" in str(exc.value)
    
    def test_too_long(self):
        with pytest.raises(ValidationError):
            validate_order_id("A" * 51)


class TestDataframeValidation:
    def test_valid_structure(self):
        columns = ["col1", "col2", "col3"]
        data = [[1, 2, 3], [4, 5, 6]]
        validate_dataframe_structure(columns, data)
        # Should not raise
    
    def test_empty_columns(self):
        with pytest.raises(ValidationError) as exc:
            validate_dataframe_structure([], [[1, 2]])
        assert "No columns" in str(exc.value)
    
    def test_empty_data(self):
        with pytest.raises(ValidationError) as exc:
            validate_dataframe_structure(["col1"], [])
        assert "No data rows" in str(exc.value)
    
    def test_duplicate_columns(self):
        with pytest.raises(ValidationError) as exc:
            validate_dataframe_structure(["col1", "col2", "col1"], [[1, 2, 3]])
        assert "Duplicate column names" in str(exc.value)
    
    def test_inconsistent_row_length(self):
        columns = ["col1", "col2", "col3"]
        data = [[1, 2, 3], [4, 5]]  # Second row missing a column
        with pytest.raises(ValidationError) as exc:
            validate_dataframe_structure(columns, data)
        assert "expected 3" in str(exc.value)


class TestTextSanitization:
    def test_normal_text(self):
        result = sanitize_text_input("Hello World")
        assert result == "Hello World"
    
    def test_null_bytes_removed(self):
        result = sanitize_text_input("Hello\x00World")
        assert result == "HelloWorld"
    
    def test_whitespace_trimmed(self):
        result = sanitize_text_input("  Hello  ")
        assert result == "Hello"
    
    def test_max_length_truncation(self):
        result = sanitize_text_input("A" * 100, max_length=10)
        assert len(result) == 10
    
    def test_empty_string(self):
        result = sanitize_text_input("")
        assert result == ""
    
    def test_none_input(self):
        result = sanitize_text_input(None)
        assert result == ""
