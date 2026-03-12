from __future__ import annotations
import logging
from typing import Any, List, Optional, Callable, Coroutine, Dict
from typing_extensions import Annotated, ParamSpec, TypeVar
from filesender.api import FileSenderClient
from typer import Typer, Option, Argument, Context, Exit
from rich import print
from rich.pretty import pretty_repr
from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from filesender.auth import Auth, UserAuth, GuestAuth
from filesender.config import get_defaults
from functools import wraps
from asyncio import run
from importlib.metadata import version
from rich.logging import RichHandler
from filesender.log import LogParam, LogLevel, configure_extra_levels
from httpx import HTTPStatusError, ConnectError, RequestError
from tenacity import RetryError

logger = logging.getLogger(__name__)

from filesender.response_types import Guest, Transfer

_err_console = Console(stderr=True)

def _handle_error(e: BaseException) -> None:
    """Prints a clean error message and exits. Avoids raw Python tracebacks."""
    # Unwrap tenacity RetryError to get the underlying exception
    if isinstance(e, RetryError):
        inner = e.last_attempt.exception()
        if inner is not None:
            _handle_error(inner)
            return
        _err_console.print(Panel("Operación fallida tras varios intentos.", title="[red]Error[/red]", border_style="red"))
        return

    if isinstance(e, HTTPStatusError):
        status = e.response.status_code
        try:
            data = e.response.json()
            msg = data.get("message", e.response.text)
        except Exception:
            msg = e.response.text or str(e)
        # Mensajes específicos de la API de FileSender
        api_messages: Dict[str, str] = {
            "auth_remote_signature_check_failed": "API Key inválida o incorrecta.\nVerifica tu API key en el perfil de FileSender.",
            "auth_remote_too_late":               "Desfase de tiempo demasiado alto.\nPrueba a añadir --delay en las opciones.",
            "guest_not_found":                    "El enlace de invitación es inválido o ha expirado.",
            "transfer_not_found":                 "El token de descarga es inválido o ha expirado.",
            "transfer_expired":                   "La transferencia ha expirado.",
        }
        if msg in api_messages:
            _err_console.print(Panel(api_messages[msg], title="[red]Error del servidor[/red]", border_style="red"))
            return
        hints: Dict[int, str] = {
            401: "Credenciales incorrectas o sesión expirada.",
            403: "Acceso denegado. Verifica tu API key.",
            404: "Recurso no encontrado. El token puede ser inválido o haber expirado.",
            500: "Error interno del servidor.",
        }
        body = f"HTTP {status}: {msg}"
        if status in hints:
            body += f"\n{hints[status]}"
        _err_console.print(Panel(body, title="[red]Error del servidor[/red]", border_style="red"))
    elif isinstance(e, (ConnectError, RequestError)):
        _err_console.print(Panel(
            f"No se pudo conectar con el servidor.\n{e}",
            title="[red]Error de conexión[/red]",
            border_style="red",
        ))
    else:
        msg = str(e)
        known: Dict[str, str] = {
            "guest_not_found":    "El enlace de invitación es inválido o ha expirado.",
            "guest_upload":       "Error en la subida por invitación.",
            "transfer_not_found": "El token de descarga es inválido o ha expirado.",
            "auth_remote":        "Error de autenticación. Revisa las credenciales.",
            "ssl":                "Error de certificado SSL. Verifica la configuración de SSL.",
        }
        detail = msg
        for key, description in known.items():
            if key in msg.lower():
                detail = description
                break
        if not detail.strip():
            detail = "Error en la comunicación con el servidor."
        _err_console.print(Panel(detail, title="[red]Error[/red]", border_style="red"))


P = ParamSpec("P")
T = TypeVar("T")
def typer_async(f: Callable[P, Coroutine[Any, Any, T]]):
    @wraps(f)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return run(f(*args, **kwargs))
        except Exception as e:
            _handle_error(e)
            raise SystemExit(1)

    return wrapper

ChunkSize = Annotated[Optional[int], Option(help="The size of each chunk to read from the input file during the upload process. Larger values will result in a faster upload but use more memory. If the value exceeds the server's maximum chunk size, this command will fail.")]
Verbose = Annotated[bool, Option(help="Enable more detailed outputs")]
Delay = Annotated[int, Option(help="Delay the signature timestamp by N seconds. Increase this value if you have a slow connection. This value should be approximately the time it takes you to upload one chunk to the server.", metavar="N")]
ConcurrentFiles = Annotated[Optional[int], Option(help="The number of files that will be uploaded concurrently.  This works multiplicatively with `concurrent_chunks`, so `concurrent_files=2, concurrent_chunks=2` means 4 total chunks of data will be stored in memory and sent concurrently.")]
ConcurrentChunks = Annotated[Optional[int], Option(help="The number of chunks that will be read from each file concurrently. Increase this number to speed up transfers, or reduce this number to reduce memory usage and network errors. This can be set to `None` to enable unlimited concurrency, but use at your own risk.")]
UploadFiles = Annotated[List[Path], Argument(file_okay=True, dir_okay=True, resolve_path=True, exists=True, help="Files and/or directories to upload")]

context: Dict[Any, Any] = {
    "default_map": get_defaults()
}
app = Typer(name="filesender", pretty_exceptions_enable=False)

def version_callback(value: bool):
    if value:
        print(version("filesender-client"))
        raise Exit()


@app.callback(context_settings=context)
def common_args(
    context: Context,
    base_url: Annotated[str, Option(help="The URL of the FileSender REST API")],
    log_level: Annotated[
        int, Option(click_type=LogParam(), help="Logging verbosity", )
    ] = LogLevel.FEEDBACK.value,
    version: Annotated[
        Optional[bool], Option("--version", callback=version_callback)
    ] = None
):
    context.obj = {
        "base_url": base_url
    }
    configure_extra_levels()
    logging.basicConfig(
        level=log_level,
        format= "%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()]
    )


@app.command(context_settings=context)
def invite(
    username: Annotated[str, Option(help="Your username. This is the username of the person doing the inviting, not the person being invited.")],
    apikey: Annotated[str, Option(help="Your API token. This is the token of the person doing the inviting, not the person being invited.")],
    recipient: Annotated[str, Argument(help="The email address of the person to invite")],
    context: Context,
    # Although these parameters are exact duplicates of those in GuestOptions,
    # typer doesn't support re-using argument lists: https://github.com/tiangolo/typer/discussions/665
    one_time: Annotated[bool, Option(help="If true, this voucher is only valid for one use, otherwise it can be re-used.")] = True,
    only_to_me: Annotated[bool, Option(help="If true, this voucher can only be used to send files to you, the person who created this voucher. Otherwise they can send files to any email address.")] = True,
    email_upload_started: Annotated[bool, Option(help="If true, an email will be sent to you, when an upload to this voucher starts.")] = False,
    email_page_access: Annotated[bool, Option(help="If true, an email will be sent to you when the guest recipient accesses the upload page.")] = False,
    email_guest_created: Annotated[bool, Option(help="If true, send an email to the guest user who is being invited to upload.")] = True,
    email_receipt: Annotated[bool, Option(help="If true, send you an email when the guest account is created.")] = True,
    email_guest_expired: Annotated[bool, Option(help="If true, send you an email when the voucher expires.")] = False,
    delay: Delay = 0
):
    """
    Invites a user to send files to you
    """
    try:
        client = FileSenderClient(
            auth=UserAuth(
                api_key=apikey,
                username=username,
                delay=delay
            ),
            base_url=context.obj["base_url"]
        )
        result: Guest = run(client.create_guest({
            "from": username,
            "recipient": recipient,
            "options": {
                "guest": {
                    "valid_only_one_time": one_time,
                    "can_only_send_to_me": only_to_me,
                    "email_upload_started": email_upload_started,
                    "email_upload_page_access": email_page_access,
                    "email_guest_created": email_guest_created,
                    "email_guest_created_receipt": email_receipt,
                    "email_guest_expired": email_guest_expired
                },
                "transfer": {
                    "add_me_to_recipients": False
                }
            }
        }))
        logger.log(LogLevel.VERBOSE.value, pretty_repr(result))
        logger.log(LogLevel.FEEDBACK.value, "Invitation successfully sent")
    except Exception as e:
        _handle_error(e)
        raise SystemExit(1)

@app.command(context_settings=context)
@typer_async
async def upload_voucher(
    files: UploadFiles,
    guest_token: Annotated[str, Option(help="The guest token. This is the part of the upload URL after 'vid='")],
    email: Annotated[str, Option(help="The email address that was invited to upload files")],
    context: Context,
    concurrent_files: ConcurrentFiles = 1,
    concurrent_chunks: ConcurrentChunks = 2,
    chunk_size: ChunkSize = None,
):
    """
    Uploads files to a voucher that you have been invited to
    """
    auth = GuestAuth(guest_token=guest_token)
    client = FileSenderClient(
        auth=auth,
        base_url=context.obj["base_url"],
        chunk_size = chunk_size,
        concurrent_files=concurrent_files,
        concurrent_chunks=concurrent_chunks
    )
    await auth.prepare(client.http_client)
    await client.prepare()
    result: Transfer = await client.upload_workflow(files, {"from": email, "recipients": []})
    logger.log(LogLevel.VERBOSE.value, pretty_repr(result))
    logger.log(LogLevel.FEEDBACK.value, "Upload completed successfully")

@app.command(context_settings=context)
@typer_async
async def upload(
    username: Annotated[str, Option(help="Username of the user performing the upload")],
    apikey: Annotated[str, Option(help="API token of the user performing the upload")],
    files: UploadFiles,
    recipients: Annotated[List[str], Option(show_default=False, help="One or more email addresses to send the files")],
    context: Context,
    concurrent_files: ConcurrentFiles = 1,
    concurrent_chunks: ConcurrentChunks = 2,
    chunk_size: ChunkSize = None,
    delay: Delay = 0
):
    """
    Sends files to an email of choice
    """
    client = FileSenderClient(
        auth=UserAuth(
            api_key=apikey,
            username=username,
            delay=delay
        ),
        base_url=context.obj["base_url"],
        chunk_size=chunk_size,
        concurrent_files=concurrent_files,
        concurrent_chunks=concurrent_chunks
    )
    await client.prepare()
    result: Transfer = await client.upload_workflow(files, {"recipients": recipients, "from": username})
    logger.log(LogLevel.VERBOSE.value, pretty_repr(result))
    logger.log(LogLevel.FEEDBACK.value, "Upload completed successfully")

@app.command(context_settings=context)
def download(
    context: Context,
    token: Annotated[str, Argument(help='The part of the download URL after "token="')],
    out_dir: Annotated[Path, Option(dir_okay=True, file_okay=False, exists=True, help="Path to the directory to store the output files")] = Path.cwd(),
):
    """Downloads all files associated with a transfer"""
    try:
        client = FileSenderClient(
            auth=Auth(),
            base_url=context.obj["base_url"],
        )
        run(client.download_files(
            token=token,
            out_dir=out_dir
        ))
        logger.log(LogLevel.FEEDBACK.value, f"Download completed successfully. Files can be found in {out_dir}")
    except Exception as e:
        _handle_error(e)
        raise SystemExit(1)

@app.command(context_settings=context)
@typer_async
async def server_info(
    context: Context,
):
    """Prints out information about the FileSender server you are interfacing with"""
    client = FileSenderClient(base_url=context.obj["base_url"])
    result = await client.get_server_info()
    logger.log(LogLevel.FEEDBACK.value, pretty_repr(result))

if __name__ == "__main__":
    app()
