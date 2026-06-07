from fastapi import APIRouter, Request

router = APIRouter(tags=["iclock"])


@router.get("/iclock/getrequest")
async def getrequest() -> str:
    return "OK"


@router.api_route("/iclock/cdata", methods=["GET", "POST"])
async def cdata(request: Request) -> str:
    print("REQUEST RECEIVED")
    print("URL:", request.url)

    body = await request.body()
    print("BODY:", body.decode(errors="ignore"))

    return "OK"


@router.post("/iclock/registry")
async def registry(request: Request) -> str:
    body = await request.body()
    print(body.decode())
    return "OK"
