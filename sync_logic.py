import requests
from msal import ConfidentialClientApplication
from azure.storage.blob import BlobServiceClient, ContentSettings

# Configuration
CLIENT_ID = "6f7cc27d-d53a-4bfc-a317-cccf93f2609a"
CLIENT_SECRET = "VE48Q~21Za2BHEMgPZQi8Qy.K5jWBAqRVHFebbwE"
TENANT_ID = "b7fc2166-4e80-4e62-a02a-814560e30976"
FOLDER_ID = "01M66LV7I6HF2A5S5R7NCLWO5BWH4H3DOR"
SHAREPOINT_SITE_NAME = "doc-ai-platform"
SHAREPOINT_HOSTNAME = "acadsigma.sharepoint.com"
CONTAINER_NAME = "test"

AZURE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=https;AccountName=sadocailibrary;"
    "AccountKey=QcIs3NdOqHRL8YVe1HoNj+0EZDnC9BBKGTU9Y3PVOgstLwvB2dpkHIMmGgOeReDWsJ0QSWh6brxa+AStMxeyUw==;"
    "EndpointSuffix=core.windows.net"
)

SCOPE = ["https://graph.microsoft.com/.default"]
last_seen_modified = {}  # You can replace this with a persistent store later

def sync_sharepoint_to_blob():
    try:
        print("\n🔁 Running sync...")

        # ------------------ AUTH ------------------
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}"
        )
        token_result = app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in token_result:
            raise Exception(f"❌ Token error: {token_result}")
        access_token = token_result["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # ------------------ GET SITE ID ------------------
        print("🔍 Searching for site...")
        site_resp = requests.get(
            f"https://graph.microsoft.com/v1.0/sites?search={SHAREPOINT_SITE_NAME}",
            headers=headers
        ).json()

        if "value" in site_resp and site_resp["value"]:
            site_id = site_resp["value"][0]["id"]
            print(f"✅ Found site via search: {site_id}")
        else:
            print("⚠️ Search failed. Trying canonical path...")
            canonical_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOSTNAME}:/sites/{SHAREPOINT_SITE_NAME}"
            site_resp = requests.get(canonical_url, headers=headers).json()

            if "id" in site_resp:
                site_id = site_resp["id"]
                print(f"✅ Found site via canonical path: {site_id}")
            else:
                raise Exception(f"❌ Site fetch failed: {site_resp}")

        # ------------------ GET DRIVE ID ------------------
        drive_resp = requests.get(f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives", headers=headers).json()
        if "value" in drive_resp and drive_resp["value"]:
            drive_id = drive_resp["value"][0]["id"]
            print(f"✅ Drive ID: {drive_id}")
        else:
            raise Exception(f"❌ Drive fetch failed: {drive_resp}")

        # ------------------ GET FILES IN FOLDER ------------------
        sp_files_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{FOLDER_ID}/children"
        sp_files_resp = requests.get(sp_files_url, headers=headers).json()

        sp_files = sp_files_resp.get("value", [])
        sp_file_map = {
            f["name"]: {
                "id": f["id"],
                "modified": f["lastModifiedDateTime"]
            }
            for f in sp_files if "file" in f
        }

        # ------------------ BLOB SETUP ------------------
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_names = {blob.name for blob in container_client.list_blobs()}

        # ------------------ SYNC FILES ------------------
        for file_name, info in sp_file_map.items():
            file_id = info["id"]
            modified_time = info["modified"]

            should_upload = (
                file_name not in blob_names or
                file_name not in last_seen_modified or
                last_seen_modified[file_name] != modified_time
            )

            if should_upload:
                print(f"⬆️ Uploading/Updating: {file_name}")
                download_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content"
                file_content = requests.get(download_url, headers=headers).content

                blob_client = container_client.get_blob_client(file_name)
                blob_client.upload_blob(
                    file_content,
                    overwrite=True,
                    content_settings=ContentSettings(content_type="application/octet-stream")
                )
                last_seen_modified[file_name] = modified_time
            else:
                print(f"✔️ Skipping unchanged: {file_name}")

        # ------------------ DELETE REMOVED FILES ------------------
        for blob_name in blob_names:
            if blob_name not in sp_file_map:
                print(f"🗑️ Deleting: {blob_name}")
                container_client.delete_blob(blob_name)
                last_seen_modified.pop(blob_name, None)

        print("✅ Sync complete.")
        return True

    except Exception as e:
        print(f"❌ Sync failed: {e}")
        return False
