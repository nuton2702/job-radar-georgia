"""Publish the exact artifact uploaded in this attempt through the Pages REST API."""
import json
import os
import time
import urllib.request
import urllib.error

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GH_TOKEN"]

def request(url, token=TOKEN, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

artifact_id = int(os.environ["PAGES_ARTIFACT_ID"])
for attempt in range(18):
    try:
        artifact = request(f"{API}/repos/{REPO}/actions/artifacts/{artifact_id}")
        if artifact.get("expired"):
            raise RuntimeError("Uploaded artifact has expired")
        if str(artifact["workflow_run"]["id"]) != os.environ["GITHUB_RUN_ID"]:
            raise RuntimeError("Artifact belongs to a different workflow run")
        break
    except urllib.error.HTTPError as exc:
        if exc.code != 404 or attempt == 17:
            raise
        time.sleep(10)

def deploy():
    oidc = request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
                   token=os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"])["value"]
    deployment = request(f"{API}/repos/{REPO}/pages/deployments", payload={
        "artifact_id": artifact_id,
        "pages_build_version": os.environ["GITHUB_SHA"],
        "oidc_token": oidc,
    })
    deployment_id = deployment["id"]
    print(f"Created Pages deployment {deployment_id} for artifact {artifact_id}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("page_url=" + deployment["page_url"] + "\n")
    for attempt in range(60):
        result = request(f"{API}/repos/{REPO}/pages/deployments/{deployment_id}")
        status = result["status"]
        if status == "deployment_failed":
            print("Pages failure details:", json.dumps(result), flush=True)
        print("Pages deployment status:", status, flush=True)
        if status == "succeed":
            break
        if status in ("deployment_failed", "deployment_content_failed", "deployment_cancelled", "deployment_lost"):
            raise RuntimeError("Pages deployment failed: " + status)
        time.sleep(5)
    else:
        raise TimeoutError("Pages deployment did not complete within five minutes")
    
for deployment_attempt in range(3):
    try:
        deploy()
        break
    except RuntimeError as exc:
        if str(exc) != "Pages deployment failed: deployment_failed" or deployment_attempt == 2:
            raise
        print("Retrying failed Pages deployment in 15 seconds", flush=True)
        time.sleep(15)
