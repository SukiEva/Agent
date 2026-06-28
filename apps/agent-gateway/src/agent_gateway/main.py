from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Gateway")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents")
    async def agents() -> list[dict[str, object]]:
        return []

    return app


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8001"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
