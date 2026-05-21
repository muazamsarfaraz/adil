"""Force adil-rag-api back to Dockerfile builder via Railway GraphQL.

Background: Railway's auto-detect (Railpack) is overriding the
``railway.toml`` builder='dockerfile' setting on the service instance
config. As a result, `railway up --service adil-rag-api` triggers
Railpack which fails with "No start command detected" and the previous
successful (older Gemini) build keeps serving production. Same fix
pattern as memory 2522/2559 for adil-document-uploader.

What this does:
  1. Reads the local CLI access token from ~/.railway/config.json.
  2. Looks up the production environment ID for the linked project.
  3. Mutates serviceInstance(serviceId, environmentId) with
     railwayConfigFile='adil-rag-api/railway.toml' so Railway honours
     the toml's builder='dockerfile' directive.
  4. Triggers a redeploy of the service so the new config takes effect.

Idempotent: re-running is safe. Doesn't touch env vars.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

PROJECT_ID = "3b3ce312-40a1-4fba-9367-6e2939ce4404"
SERVICE_ID = "2f4a5050-3d4f-46ca-9b0f-29802d04abe3"  # adil-rag-api
SERVICE_NAME = "adil-rag-api"

# rootDirectory is already 'adil-rag-api' on this service per memory 2398/2402.
# railway.toml lives at adil-rag-api/railway.toml from repo root. Once we
# point railwayConfigFile at it, Railway picks builder='dockerfile' from
# inside the toml and stops trying to Railpack-detect.
CONFIG_FILE_PATH = "adil-rag-api/railway.toml"

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"


def read_token() -> str:
    cfg_path = Path(os.environ["USERPROFILE"]) / ".railway" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    token = cfg.get("user", {}).get("accessToken")
    if not token:
        sys.exit("No accessToken found in ~/.railway/config.json — run 'railway login' first.")
    return token


def gql(token: str, query: str, variables: dict) -> dict:
    resp = httpx.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload and payload["errors"]:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def get_production_env_id(token: str) -> str:
    data = gql(
        token,
        """
        query($id: String!) {
          project(id: $id) {
            environments {
              edges { node { id name } }
            }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    edges = data["project"]["environments"]["edges"]
    for e in edges:
        n = e["node"]
        if n["name"].lower() == "production":
            return n["id"]
    raise RuntimeError(f"No 'production' environment found in: {[e['node']['name'] for e in edges]}")


def get_service_instance(token: str, environment_id: str) -> dict:
    data = gql(
        token,
        """
        query($serviceId: String!, $environmentId: String!) {
          serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
            id
            builder
            rootDirectory
            railwayConfigFile
            startCommand
          }
        }
        """,
        {"serviceId": SERVICE_ID, "environmentId": environment_id},
    )
    return data["serviceInstance"]


def update_service_instance(token: str, environment_id: str) -> dict:
    data = gql(
        token,
        """
        mutation($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
          serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input)
        }
        """,
        {
            "serviceId": SERVICE_ID,
            "environmentId": environment_id,
            "input": {
                "railwayConfigFile": CONFIG_FILE_PATH,
                "rootDirectory": "adil-rag-api",
                # Builder remains in the toml — Railway picks it up via the
                # railwayConfigFile pointer above.
            },
        },
    )
    return data


def trigger_redeploy(token: str, environment_id: str) -> dict:
    """Trigger a fresh deploy of the latest source via GraphQL."""
    data = gql(
        token,
        """
        mutation($input: ServiceInstanceDeployInput!) {
          serviceInstanceDeployV2(input: $input)
        }
        """,
        {
            "input": {
                "serviceId": SERVICE_ID,
                "environmentId": environment_id,
            },
        },
    )
    return data


def main() -> int:
    token = read_token()

    print(f"== adil-rag-api builder fix ({SERVICE_ID[:8]}…) ==")

    print("\n[1/4] Resolving production environment id…")
    env_id = get_production_env_id(token)
    print(f"  environment id: {env_id}")

    print("\n[2/4] Current service instance config:")
    before = get_service_instance(token, env_id)
    print(json.dumps(before, indent=2))

    print(f"\n[3/4] Updating: railwayConfigFile -> '{CONFIG_FILE_PATH}'")
    result = update_service_instance(token, env_id)
    print(f"  serviceInstanceUpdate returned: {result}")

    after = get_service_instance(token, env_id)
    print("\n  config after update:")
    print(json.dumps(after, indent=2))

    if after.get("railwayConfigFile") != CONFIG_FILE_PATH:
        print(f"\n  ! WARNING: railwayConfigFile is {after.get('railwayConfigFile')!r}, expected {CONFIG_FILE_PATH!r}")

    print("\n[4/4] Triggering redeploy…")
    try:
        deploy = trigger_redeploy(token, env_id)
        print(f"  deploy result: {deploy}")
    except Exception as exc:
        print(f"  redeploy via GraphQL failed: {exc}")
        print("  (run 'railway up --service adil-rag-api' from repo root instead.)")
        return 1

    print("\n✅ Done. Watch the build at:")
    print(f"  https://railway.com/project/{PROJECT_ID}/service/{SERVICE_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
