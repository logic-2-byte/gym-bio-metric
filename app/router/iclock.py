from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["iclock"])


user_action = "disable"  # Set to "disable" or "enable" to control user status
command_sent = False


@router.api_route("/iclock/getrequest", methods=["GET", "POST"])
async def getrequest(request: Request) -> PlainTextResponse:
    global command_sent
    if request.method == "GET":
        if not command_sent:
            command_sent = True
            if user_action == "enable":
                print("GETREQUEST (GET) hit - sending enable user 111 command")
                return PlainTextResponse(
                    "C:1:DATA UPDATE USERINFO PIN=111\tGrp=1\n",
                    media_type="text/plain"
                )
            print("GETREQUEST (GET) hit - sending disable user 111 command")
            return PlainTextResponse(
                "C:1:DATA UPDATE USERINFO PIN=111\tGrp=3\n",
                media_type="text/plain"
            )
        return PlainTextResponse("OK", media_type="text/plain")
    body = await request.body()
    print("GETREQUEST:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/cdata", methods=["GET", "POST"])
async def cdata(request: Request) -> PlainTextResponse:
    print("CDATA RECEIVED")
    print("URL:", request.url)
    print("QUERY:", request.query_params)
    body = await request.body()
    print("BODY:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/registry", methods=["GET", "POST"])
async def registry(request: Request) -> PlainTextResponse:
    body = await request.body()
    print("REGISTRY:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/devicecmd", methods=["GET", "POST"])
async def devicecmd(request: Request) -> PlainTextResponse:
    print("DEVICECMD RECEIVED")
    print("URL:", request.url)
    print("QUERY:", request.query_params)
    body = await request.body()
    print("BODY:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")
