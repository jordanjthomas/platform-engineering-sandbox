from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    admin_token: str = ""
    log_level: str = "INFO"
    k8s_in_cluster: bool = True

    model_config = {"env_prefix": ""}


settings = Settings()
