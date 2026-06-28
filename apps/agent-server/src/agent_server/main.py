from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Server")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
