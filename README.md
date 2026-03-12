# FileSender CLI — Docker Wrapper 

A Dockerized wrapper around the [WEHI FileSenderCli](https://github.com/WEHI-ResearchComputing/FileSenderCli) Python client, providing a simple configuration-driven interface for uploading, downloading, and managing guest invitations on any [FileSender](https://filesender.org) instance.

## Features

| Operation          | Description                                  | Requires API key |
|--------------------|----------------------------------------------|:----------------:|
| `upload`           | Upload files to a specific recipient         | Yes              |
| `upload_voucher`   | Upload files using a guest invitation link   | No               |
| `download`         | Download files using a transfer token        | No               |
| `invite`           | Send an upload invitation to someone         | Yes              |

## Prerequisites

- Access to a FileSender instance (base URL, and optionally an API key)
- **Docker** (recommended) — [Docker](https://docs.docker.com/get-docker/) and Docker Compose, or
- **Python 3.10+** — if you prefer to run locally without Docker (see [Running Without Docker](#running-without-docker))

## Quick Start

### 1. Configure credentials

Edit `filesender.ini` with your FileSender instance details:

```ini
[system]
base_url = https://your-filesender-instance.example.com

[user]
username = your_username@example.com
apikey   = your_api_key_here
```

> **Note:** `base_url` must be the instance domain only, **without** `/rest.php` — the client appends it automatically.

> **Note:** `username` and `apikey` are only required for `upload` and `invite` modes. If you only need to upload via an invitation link (`upload_voucher`) or download a file (`download`), you can leave those fields blank.

### 2. Configure the operation

Each operation reads its parameters from a file in `config/`. Edit the appropriate file before running:

| File                          | Operation          |
|-------------------------------|--------------------|
| `config/upload.flags`         | `upload`           |
| `config/upload_voucher.flags` | `upload_voucher`   |
| `config/download.flags`       | `download`         |
| `config/invite.flags`         | `invite`           |

See [Flag Files Reference](#flag-files-reference) below for details on each file.

### 3. Build and run

```bash
# Build the Docker image (first time or after changes)
docker compose build

# Upload files to a recipient
docker compose run --rm filesender upload

# Upload files using a guest invitation link
docker compose run --rm filesender upload_voucher

# Download files using a transfer token
docker compose run --rm filesender download

# Send an upload invitation
docker compose run --rm filesender invite
```

To preview the resolved command without executing it:

```bash
docker compose run --rm filesender upload -- --dry-run
```

## Flag Files Reference

### `config/upload.flags`

```
--recipients recipient@example.com
uploads/your_file
```

| Parameter      | Description                              |
|----------------|------------------------------------------|
| `--recipients` | Recipient email(s), comma-separated      |
| File path      | Relative path to the file(s) to upload   |

### `config/upload_voucher.flags`

```
--guest-token YOUR_GUEST_TOKEN_HERE
--email guest@example.com
uploads/your_file
```

| Parameter       | Description                                                         |
|-----------------|---------------------------------------------------------------------|
| `--guest-token` | The `vid=` value from the guest invitation URL (see note below)     |
| `--email`       | The email address that received the invitation                      |
| File path       | Relative path to the file(s) to upload                              |

> **Where to find the token:** When you receive an upload invitation by email, the link will look like:
> `https://filesender.example.com/?s=upload&vid=f7874954-9a4b-41ec-a69a-fb8f95481304`
> The `--guest-token` value is everything after `vid=`.

### `config/download.flags`

```
YOUR_DOWNLOAD_TOKEN_HERE
--out-dir downloads
```

| Parameter   | Description                                                       |
|-------------|-------------------------------------------------------------------|
| Token       | The `token=` value from the download URL (positional argument)    |
| `--out-dir` | Output directory for downloaded files                             |

> **Where to find the token:** When you receive a download link, it will look like:
> `https://filesender.example.com/?s=download&token=ff6d4cb4-c84a-4b46-91ab-f642effd9992`
> The token is everything after `token=`.

### `config/invite.flags`

```
recipient@example.com
```

| Parameter | Description                          |
|-----------|--------------------------------------|
| Recipient | Email of the person to invite        |

### Flags file syntax

- Arguments are separated by spaces or newlines
- Single and double quotes are supported
- Lines starting with `#` are comments
- Line continuation with trailing `\`

## Running Without Docker

```bash
# Install the client (once)
pip install ./FileSenderCli/

# Run any operation
python3.11 filesender-wehi--config.py upload
python3.11 filesender-wehi--config.py upload_voucher
python3.11 filesender-wehi--config.py download
python3.11 filesender-wehi--config.py invite
```

## Project Structure

```
.
├── Dockerfile                  # Python 3.11 image with the CLI client
├── docker-compose.yml          # Service definition and volume mounts
├── filesender.ini              # Credentials and instance URL
├── filesender-wehi--config.py  # Wrapper script (reads .ini and .flags)
├── config/
│   ├── upload.flags            # Parameters for upload
│   ├── upload_voucher.flags    # Parameters for upload_voucher
│   ├── download.flags          # Parameters for download
│   └── invite.flags            # Parameters for invite
├── uploads/                    # Place files to upload here
├── downloads/                  # Downloaded files are saved here
└── FileSenderCli/              # Bundled WEHI client source
```

## License

The bundled [FileSenderCli](https://github.com/WEHI-ResearchComputing/FileSenderCli) is licensed under BSD-3-Clause. See its source for details.

