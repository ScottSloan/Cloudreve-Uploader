import os
import time
import mimetypes
import asyncio
import aiohttp

class CloudreveUploader:
    def __init__(self, api_url: str, email: str, password: str, storage_policy_id: str, version: str):
        self.api_url = api_url
        self.email = email
        self.password = password
        self.storage_policy_id = storage_policy_id
        self.version = version

        self.access_token = ""

    async def init(self):
        await self.get_access_token()

    async def get_access_token(self):
        url = f"{self.api_url}/session/token"

        body = {
            "email": self.email,
            "password": self.password
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers = self.get_headers(), json = body) as resp:
                data = await resp.json()

                if data["code"] == 0:
                    self.access_token = data["data"]["token"]["access_token"]
        
    async def create_upload_session(self, file_path: str):
        url = f"{self.api_url}/file/upload"

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=self.get_headers(), json = self.get_upload_body(file_path)) as resp:
                data = await resp.json()

                if data["code"] == 0:
                    return {
                        "session_id": data["data"]["session_id"],
                        "callback_secret": data["data"]["callback_secret"],
                        "upload_url": data["data"]["upload_urls"][0]
                    }

    async def upload_file_in_chunks(self, upload_url: str, file_path: str, chunk_size: int = 3276800):
        file_size = os.path.getsize(file_path)

        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                start = 0

                while start < file_size:
                    end = min(start + chunk_size, file_size) - 1
                    f.seek(start)
                    chunk_data = f.read(end - start + 1)

                    headers = {
                        "Content-Length": str(end - start + 1),
                        "Content-Range": f"bytes {start}-{end}/{file_size}"
                    }

                    async with session.put(upload_url, headers = headers, data = chunk_data) as resp:
                        if resp.status in [200, 201]:
                            return await resp.json()
                        elif resp.status in [202]:
                            start = end + 1
                        else:
                            return None

    async def upload_callback(self, session_id: str, callback_secret: str, file_name: str):
        url = f"{self.api_url}/callback/onedrive/{session_id}/{callback_secret}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers = self.get_headers()) as resp:
                data = await resp.json()

                if data["code"] == 0:
                    print(f"上传成功：{file_name}")
                else:
                    print("回调上传失败：", data)

    async def create_direct_link(self, file_list: list):
        url = f"{self.api_url}/file/source"

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers = self.get_headers(), json = self.get_uri_body(file_list)) as resp:
                data = await resp.json()

                if data["code"] == 0:
                    return data["data"]
                else:
                    print("创建直链失败：", data)

    async def upload_file(self, file_path: str):
        session_info = await self.create_upload_session(file_path)
        if not session_info:
            print(f"创建上传会话失败：{file_path}")
            return

        result = await self.upload_file_in_chunks(session_info["upload_url"], file_path)

        if not result:
            print(f"上传文件失败，重试一次：{file_path}")
            
            result = await self.upload_file_in_chunks(session_info["upload_url"], file_path)

            if not result:
                print("上传文件失败：", file_path)
                return

        await self.upload_callback(session_info["session_id"], session_info["callback_secret"], os.path.basename(file_path))

    async def upload_files(self, file_list: list):
        for file_path in file_list:
            print("上传文件：", file_path)
            await self.upload_file(file_path)

        await self.create_direct_link(file_list)

    def get_headers(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
        }

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        return headers
    
    def get_upload_body(self, file_path: str):
        return {
            "uri": f"cloudreve://my/Bili23_Downloader/{self.version}/{os.path.basename(file_path)}",
            "size": os.path.getsize(file_path),
            "policy_id": self.storage_policy_id,
            "last_modified": int(time.time() * 1000),
            "mime_type": self.generate_mime_type(file_path)
        }
    
    def get_uri_body(self, file_list: list):
        return {
            "uris": [
                f"cloudreve://my/Bili23_Downloader/{self.version}/{os.path.basename(file_name)}" for file_name in file_list
            ]
        }

    def generate_mime_type(self, file_path: str):
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type

if __name__ == "__main__":
    cloudreve_api = os.getenv("CLOUDREVE_API")
    cloudreve_email = os.getenv("CLOUDREVE_EMAIL")
    cloudreve_password = os.getenv("CLOUDREVE_PASSWORD")
    cloudreve_storage_policy_id = os.getenv("CLOUDREVE_STORAGE_POLICY_ID")

    version = os.getenv("VERSION")

    files_to_upload = [
        f"Bili23_Downloader-{version}-windows-x64.zip",
        f"Bili23_Downloader-{version}-windows-x64-setup.exe",
        f"Bili23_Downloader-{version}-linux-amd64.deb"
    ]

    async def main():
        uploader = CloudreveUploader(cloudreve_api, cloudreve_email, cloudreve_password, cloudreve_storage_policy_id, version)
        await uploader.init()
        await uploader.upload_files(files_to_upload)

    asyncio.run(main())
    