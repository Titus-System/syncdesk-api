if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:create_app",
        host="127.0.0.1",
        port=8000,
        ws_max_size= 4 * 1024, # Limits websocket payload to 4KB
        reload=True,
        factory=True
    )
