from pydantic import BaseModel, Field
class ReportInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    job_id: int
    destination: str = Field(default='业务复核组', min_length=2, max_length=120)
    groups: list[str] = Field(default_factory=list, max_length=20)
    interval_seconds: int = Field(default=86400, ge=60, le=2592000)
    delay_seconds: int = Field(default=0, ge=0, le=2592000)
class SignInput(BaseModel):
    group: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=500)
class CorrectionInput(BaseModel):
    job_id: int
    note: str = Field(default='', max_length=500)
