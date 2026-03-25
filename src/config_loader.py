import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class NetworkConfig(BaseModel):
    """Network and retry configuration."""
    max_retries: int = Field(default=3, ge=1, le=10)
    max_retries_limit: int = Field(default=10, ge=1, le=20)
    base_delay_seconds: float = Field(default=1.0, gt=0)
    timeout_seconds: int = Field(default=10, ge=1, le=60)

    @field_validator('max_retries_limit')
    @classmethod
    def limit_must_be_greater_than_retries(cls, v: int, info) -> int:
        data = info.data
        if 'max_retries' in data and v < data['max_retries']:
            raise ValueError('max_retries_limit must be >= max_retries')
        return v


class DataSourceConfig(BaseModel):
    """External data source URLs."""
    amfi_nav_url: str = Field(default="https://www.amfiindia.com/spages/NAVAll.txt")


class Settings(BaseModel):
    """Root settings model for FinAgent configuration."""
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    data_sources: DataSourceConfig = Field(default_factory=DataSourceConfig)


class ConfigLoader:
    """Loads and validates configuration from config/settings.json."""
    
    DEFAULT_CONFIG = Settings()
    
    @classmethod
    def load(cls, config_path: Path | str | None = None) -> Settings:
        """Load configuration from file or return defaults.
        
        Args:
            config_path: Optional path to config file. If not provided,
                        searches in standard locations.
                        
        Returns:
            Validated Settings object
        """
        if config_path is None:
            config_path = cls._find_config_file()
        
        if config_path is None or not Path(config_path).exists():
            return cls.DEFAULT_CONFIG
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return Settings.model_validate(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return cls.DEFAULT_CONFIG
        except Exception:
            return cls.DEFAULT_CONFIG
    
    @classmethod
    def _find_config_file(cls) -> Path | None:
        """Search for config file in standard locations."""
        search_paths = [
            Path("config/settings.json"),
            Path("../config/settings.json"),
            Path(__file__).parent.parent / "config" / "settings.json",
        ]
        
        for path in search_paths:
            if path.exists():
                return path
        
        return None


# Module-level singleton for lazy loading
_config: Settings | None = None


def get_config() -> Settings:
    """Get the global configuration instance.
    
    Lazily loads config on first call.
    """
    global _config
    if _config is None:
        _config = ConfigLoader.load()
    return _config


def reload_config() -> Settings:
    """Force reload configuration from file."""
    global _config
    _config = ConfigLoader.load()
    return _config
