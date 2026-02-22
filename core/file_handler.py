# Standard library and internal project imports for data manipulation, configuration, and validation.
# Integrates with: pandas for CSV/Excel parsing and utils/validators.py for security checks.
import pandas as pd
from typing import Dict, Any
from config.settings import COMMON_REVIEW_COLUMNS, RATING_COLUMNS, DATE_COLUMNS
from utils.logger import setup_logger
from utils.exceptions import FileProcessingError, ValidationError
from utils.validators import validate_file_extension, validate_file_size, validate_dataframe_structure

# Initialize the file handler logger.
# Integrates with: utils/logger.py for tracking file upload events and parsing failures.
logger = setup_logger(__name__)


# Primary class for reading, validating, and extracting relevant columns from raw files.
# Integrates with: main.py (/api/upload) to convert binary uploads into structured report data.
class FileHandler:
    def process_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Parse uploaded file, detect column types, return structured data
        for the Analyzer and for the frontend preview.
        
        Raises:
            FileProcessingError: If file cannot be processed
            ValidationError: If file validation fails
        """
        import io
        
        logger.info(f"Processing file: {filename}, size: {len(file_content)} bytes")
        
        try:
            # 1. Pre-processing validation: Ensure file extension and size are safe.
            # Integrates with: config/environments.py for security policy enforcement.
            try:
                from config.environments import config
                validate_file_extension(filename, config.security.allowed_file_extensions)
                validate_file_size(len(file_content), config.security.max_file_size_mb)
            except ValidationError as e:
                logger.warning(f"File validation failed: {e.message}")
                return {"error": e.message}
            
            # 2. Binary parsing logic: Detect and read CSV or Excel files.
            # Integrates with: pandas for robust tabular data extraction.
            if filename.endswith(".csv"):
                df = None
                # Try common delimiters to handle diverse CSV formats.
                for sep in [",", ";", "\t"]:
                    try:
                        df = pd.read_csv(io.BytesIO(file_content), sep=sep)
                        if len(df.columns) > 1:
                            logger.debug(f"Successfully parsed CSV with separator: {repr(sep)}")
                            break
                    except Exception as e:
                        logger.debug(f"Failed to parse with separator {repr(sep)}: {e}")
                        continue
                
                if df is None or len(df.columns) <= 1:
                    raise FileProcessingError("Could not parse CSV file with any common delimiter")
                    
            elif filename.endswith((".xls", ".xlsx")):
                df = pd.read_excel(io.BytesIO(file_content))
                logger.debug(f"Successfully parsed Excel file")
            else:
                raise ValidationError(
                    "Unsupported file format. Please upload CSV or Excel.",
                    details={"filename": filename}
                )

            # Prevent processing of empty files.
            if df.empty:
                raise ValidationError("The uploaded file is empty.")

            # Issue a warning if data volume is low.
            warning = None
            if len(df) < 10:
                warning = (
                    f"Only {len(df)} reviews found. Results may not be statistically meaningful "
                    "(recommended: 10+ reviews)."
                )

            # 3. Internal Column Detection: Find matching headers for text, ratings, and dates.
            # Integrates with: config/settings.py candidate lists.
            def _find_col(candidates):
                col_lower = [c.strip().lower() for c in df.columns]
                # Exact case-insensitive matching.
                for cand in candidates:
                    if cand.lower() in col_lower:
                        return df.columns[col_lower.index(cand.lower())]
                # Partial fuzzy matching.
                for cand in candidates:
                    for i, col in enumerate(col_lower):
                        if cand.lower() in col:
                            return df.columns[i]
                return None

            # Map detected columns for use by the Analyzer module.
            review_col = _find_col(COMMON_REVIEW_COLUMNS)
            if review_col is None:
                # Auto-fallback to the first text-like column if no header matches.
                str_cols = df.select_dtypes(include=["object", "string"]).columns
                review_col = str_cols[0] if len(str_cols) > 0 else df.columns[0]

            rating_col = _find_col(RATING_COLUMNS)
            date_col = _find_col(DATE_COLUMNS)

            # 4. Generate volume timeline data for the frontend chart.
            # Integrates with: Chart.js on the frontend via result JSON.
            volume_data = {}
            if date_col:
                try:
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                    valid = df.dropna(subset=[date_col])
                    if not valid.empty:
                        daily = valid[date_col].dt.date.value_counts().sort_index()
                        volume_data = {
                            "labels": [d.strftime("%Y-%m-%d") for d in daily.index],
                            "values": daily.values.tolist(),
                        }
                except Exception:
                    # Fail gracefully if date parsing errors occur.
                    pass

            # Convert dataframe to primitive Python types for JSON serialization.
            columns = df.columns.tolist()
            df = df.fillna("")
            data_rows = df.values.tolist()
            
            # Final structural validation.
            # Integrates with: utils/validators.py to ensure the payload is safe for consumption.
            try:
                validate_dataframe_structure(columns, data_rows)
            except ValidationError as e:
                logger.error(f"Dataframe validation failed: {e.message}")
                return {"error": e.message}
            
            logger.info(f"Successfully processed file: {len(data_rows)} rows, {len(columns)} columns")

            # Assemble final processing result.
            # Integrates with: main.py response model.
            return {
                "columns": columns,
                "data": data_rows,
                "auto_detected_column": review_col,
                "rating_column": rating_col,
                "date_column": date_col,
                "volume_data": volume_data,
                "warning": warning,
            }

        # Error wrapping to ensure user-friendly messages for parsing failures.
        except (ValidationError, FileProcessingError) as e:
            logger.error(f"File processing error: {e.message}", exc_info=True)
            return {"error": e.message}
        except Exception as e:
            logger.error(f"Unexpected error processing file: {str(e)}", exc_info=True)
            return {"error": f"Error processing file: {str(e)}"}
