from pydantic import BaseModel, Field


class UiFallback(BaseModel):
    component: str
    props: dict[str, object] = Field(default_factory=dict)


class UiDescriptor(BaseModel):
    schema_version: str = "ui.v1"
    component: str
    component_version: str = "v1"
    props: dict[str, object] = Field(default_factory=dict)
    fallback: UiFallback
