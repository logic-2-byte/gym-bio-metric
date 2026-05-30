from fastapi import APIRouter, Request

router = APIRouter(tags=["iclock"])


@router.get("/iclock/getrequest")
async def getrequest() -> str:
    return "OK"


@router.get("/iclock/cdata")
async def cdata() -> str:
    return "OK"


@router.post("/iclock/cdata")
async def upload(request: Request) -> str:
    body = await request.body()
    print(body.decode())
    return "OK"


@router.post("/iclock/registry")
async def registry(request: Request) -> str:
    body = await request.body()
    print(body.decode())
    return "OK"
