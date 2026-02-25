"""
Tests for file handler.
"""
import pytest
import io
from core.file_handler import FileHandler


class TestFileHandler:
    def test_process_csv_file(self, sample_csv_content):
        handler = FileHandler()
        result = handler.process_file(sample_csv_content, "test.csv")
        
        assert "columns" in result
        assert "data" in result
        assert "auto_detected_column" in result
        assert len(result["columns"]) == 3
        assert len(result["data"]) == 5
    
    def test_unsupported_file_format(self):
        handler = FileHandler()
        result = handler.process_file(b"test", "test.txt")
        
        assert "error" in result
        assert "not allowed" in result["error"].lower()
    
    def test_empty_file(self):
        handler = FileHandler()
        csv_data = b"col1,col2\n"
        result = handler.process_file(csv_data, "empty.csv")
        
        assert "error" in result
        assert "empty" in result["error"].lower()
    
    def test_low_review_warning(self):
        handler = FileHandler()
        csv_data = b"review_text,rating\n\"Test review 1\",5\n\"Test review 2\",4\n"
        result = handler.process_file(csv_data, "small.csv")
        
        assert "warning" in result
        assert "10+ reviews" in result["warning"]
    
    def test_column_detection(self, sample_csv_content):
        handler = FileHandler()
        result = handler.process_file(sample_csv_content, "test.csv")
        
        assert result["auto_detected_column"] == "review_text"
        assert result["rating_column"] == "rating"
        assert result["date_column"] == "date"
