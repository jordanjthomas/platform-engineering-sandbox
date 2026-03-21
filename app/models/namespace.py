import re

from pydantic import BaseModel, field_validator

RESERVED_NAMES = {"default", "platform"}
DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class QuotaSpec(BaseModel):
    cpu_requests: str | None = None
    cpu_limits: str | None = None
    memory_requests: str | None = None
    memory_limits: str | None = None
    pods: int | None = None


class QuotaDefaults(BaseModel):
    cpu_requests: str
    cpu_limits: str
    memory_requests: str
    memory_limits: str
    pods: int

    @classmethod
    def for_environment(cls, environment: str) -> "QuotaDefaults":
        if environment == "prod":
            return cls(
                cpu_requests="2",
                cpu_limits="4",
                memory_requests="2Gi",
                memory_limits="4Gi",
                pods=20,
            )
        return cls(
            cpu_requests="1",
            cpu_limits="2",
            memory_requests="1Gi",
            memory_limits="2Gi",
            pods=10,
        )

    def merge(self, overrides: QuotaSpec | None) -> "QuotaDefaults":
        if overrides is None:
            return self
        return QuotaDefaults(
            cpu_requests=overrides.cpu_requests or self.cpu_requests,
            cpu_limits=overrides.cpu_limits or self.cpu_limits,
            memory_requests=overrides.memory_requests or self.memory_requests,
            memory_limits=overrides.memory_limits or self.memory_limits,
            pods=overrides.pods if overrides.pods is not None else self.pods,
        )


class CreateNamespaceRequest(BaseModel):
    name: str
    team: str
    environment: str
    quota: QuotaSpec | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not DNS_LABEL_RE.match(v):
            raise ValueError(
                "Must be a valid RFC 1123 DNS label: lowercase alphanumeric "
                "and hyphens, 1-63 chars, no leading/trailing hyphens"
            )
        if v.startswith("kube-"):
            raise ValueError("Names starting with 'kube-' are reserved")
        if v in RESERVED_NAMES:
            raise ValueError(f"'{v}' is a reserved namespace name")
        return v


class QuotaUsage(BaseModel):
    hard: str
    used: str


class NamespaceSummary(BaseModel):
    name: str
    team: str
    environment: str
    created_at: str


class NamespaceDetail(BaseModel):
    name: str
    team: str
    environment: str
    created_at: str
    quota: dict[str, QuotaUsage]
