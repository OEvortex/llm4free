import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from os import getcwd, makedirs, path
from threading import Thread
from time import sleep
from typing import Any, Optional, Tuple, Union

from colorama import Fore
from llm4free.browser_requests._http.compat import Session
from tqdm import tqdm

from llm4free.litagent import LitAgent
try:
    try:
        from llm4free.swiftcli import CLI, option, argument  # type: ignore
    except Exception:
        raise ImportError("swiftcli is required for this CLI")
except Exception:
    class CLI:
        def __init__(self,*a,**k): pass
        def command(self,*a,**k): return lambda f: f
        def run(self): pass
    option = lambda *a, **k: (lambda f: f)
    argument = lambda *a, **k: (lambda f: f)
from llm4free.version import __prog__

# Define cache directory using tempfile
user_cache_dir = os.path.join(tempfile.gettempdir(), "llm4free")
if not os.path.exists(user_cache_dir):
    os.makedirs(user_cache_dir)


session = Session()

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": LitAgent().random(),
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "referer": "https://y2mate.com",
}

session.headers.update(headers)


def get_excep(e):
    return e.args[1] if len(e.args) > 1 else e


appdir = user_cache_dir

if not path.isdir(appdir):
    try:
        makedirs(appdir)
    except Exception as e:
        print(f"Error : {get_excep(e)}  while creating site directory - " + appdir)

history_path = path.join(appdir, "history.json")


class utils:
    @staticmethod
    def error_handler(resp=None, exit_on_error=False, log=True):
        r"""Execption handler decorator"""

        def decorator(func):
            def main(*args, **kwargs):
                try:
                    try:
                        return func(*args, **kwargs)
                    except KeyboardInterrupt:
                        print()
                        exit(1)
                except Exception as e:
                    if log:
                        raise Exception(f"Error - {get_excep(e)}")
                    if exit_on_error:
                        exit(1)

                    return resp

            return main

        return decorator

    @staticmethod
    def get(*args, **kwargs):
        r"""Sends http get request"""
        resp = session.get(*args, **kwargs)
        return all([resp.ok, "application/json" in resp.headers["content-type"]]), resp

    @staticmethod
    def post(*args, **kwargs):
        r"""Sends http post request"""
        resp = session.post(*args, **kwargs)
        return all([resp.ok, "application/json" in resp.headers["content-type"]]), resp

    @staticmethod
    def add_history(data: dict) -> None:
        """Adds entry to history
        :param data: Response of `third query`
        :type data: dict
        :rtype: None
        """
        try:
            if not path.isfile(history_path):
                data1: dict[str, list[Any]] = {__prog__: []}
                with open(history_path, "w") as fh:
                    json.dump(data1, fh)
            with open(history_path) as fh:
                saved_data = json.load(fh).get(__prog__)
            data["datetime"] = datetime.now().strftime("%c")
            saved_data.append(data)
            with open(history_path, "w") as fh:
                json.dump({__prog__: saved_data}, fh, indent=4)
        except Exception:
            pass

    @staticmethod
    def get_history(dump: bool = False) -> Union[list, str]:
        r"""Loads download history
        :param dump: (Optional) Return whole history as str
        :type dump: bool
        :rtype: list|str
        """
        try:
            resp = []
            if not path.isfile(history_path):
                data1: dict[str, list[Any]] = {__prog__: []}
                with open(history_path, "w") as fh:
                    json.dump(data1, fh)
            with open(history_path) as fh:
                if dump:
                    return json.dumps(json.load(fh), indent=4)
                entries = json.load(fh).get(__prog__)
            for entry in entries:
                resp.append(entry.get("vid"))
            return resp
        except Exception:
            return []


class first_query:
    raw: dict
    vitems: list
    vid: str
    title: str

    def __init__(self, query: str):
        r"""Initializes first query class
        :param query: Video name or youtube link
        :type query: str
        """
        self.query_string = query
        self.url = "https://www.y2mate.com/mates/analyzeV2/ajax"
        self.payload = self.__get_payload()
        self.processed = False
        self.is_link = False
        self.raw = {}
        self.vitems = []
        self.vid = ""
        self.title = ""

    def __get_payload(self):
        return {
            "hl": "en",
            "k_page": "home",
            "k_query": self.query_string,
            "q_auto": "0",
        }

    def __str__(self):
        return """
{
    "page": "search",
    "status": "ok",
    "keyword": "happy birthday",
    "vitems": [
        {
            "v": "_z-1fTlSDF0",
            "t": "Happy Birthday song"
        },
     ]
}"""

    def __enter__(self, *args, **kwargs):
        return self.__call__(*args, **kwargs)

    def __exit__(self, *args, **kwargs):
        self.processed = False

    def __call__(self, timeout: int = 30):
        return self.main(timeout)

    def main(self, timeout=30):
        r"""Sets class attributes
        :param timeout: (Optional) Http requests timeout
        :type timeout: int
        """
        okay_status, resp = utils.post(self.url, data=self.payload, timeout=timeout)
        # print(resp.headers["content-type"])
        # print(resp.content)
        if okay_status:
            dict_data = resp.json()
            self.__setattr__("raw", dict_data)
            for key in dict_data.keys():
                self.__setattr__(key, dict_data.get(key))
            self.is_link = not hasattr(self, "vitems")
            self.processed = True
        else:
            raise Exception(f"First query failed - [{resp.status_code} : {resp.reason}]")
        return self


class second_query:
    vid: str
    a: str
    title: str
    video: dict
    audio: dict
    related: list
    raw: dict
    video_dict: Optional[dict]

    def __init__(self, query_one: first_query, item_no: int = 0):
        r"""Initializes second_query class
        :param query_one: Query_one class
        :type query_one: object
        :param item_no: (Optional) Query_one.vitems index
        :type item_no: int
        """
        assert query_one.processed, "First query failed"

        self.query_one = query_one
        self.item_no = item_no
        self.processed = False
        self.video_dict = None
        self.url = "https://www.y2mate.com/mates/analyzeV2/ajax"
        self.vid = ""
        self.a = ""
        self.title = ""
        self.video = {}
        self.audio = {}
        self.related = []
        self.raw = {}

    def __str__(self):
        return """
{
    "status": "ok",
    "mess": "",
    "page": "detail",
    "vid": "_z-1fTlSDF0",
    "extractor": "youtube",
    "title": "Happy Birthday song",
    "t": 62,
    "a": "infobells",
    "links": {
        "mp4": {
            "136": {
                "size": "5.5 MB",
                "f": "mp4",
                "q": "720p",
                "q_text": "720p (.mp4) <span class=\"label label-primary\"><small>m-HD</small></span>",
                "k": "joVBVdm2xZWhaZWhu6vZ8cXxAl7j4qpyhNgqkwx0U/tcutx/harxdZ8BfPNcg9n1"
            },
         },
        "mp3": {
            "140": {
                "size": "975.1 KB",
                "f": "m4a",
                "q": ".m4a",
                "q_text": ".m4a (128kbps)",
                "k": "joVBVdm2xZWhaZWhu6vZ8cXxAl7j4qpyhNhuxgxyU/NQ9919mbX2dYcdevRBnt0="
            },
         },
    "related": [
        {
            "title": "Related Videos",
            "contents": [
                {
                    "v": "KK24ZvxLXGU",
                    "t": "Birthday Songs - Happy Birthday To You | 15 minutes plus"
                },
   ]
        }
    ]
}
            """

    def get_item(self, item_no: Optional[int] = None):
        r"""Return specific items on `self.query_one.vitems`"""
        if self.video_dict:
            return self.video_dict
        if self.query_one.is_link:
            return {"v": self.query_one.vid, "t": self.query_one.title}
        all_items = self.query_one.vitems
        assert self.item_no < len(all_items) - 1, (
            "The item_no  is greater than largest item's index -  try lower value"
        )

        return self.query_one.vitems[item_no or self.item_no]

    def get_payload(self):
        return {
            "hl": "en",
            "k_page": "home",
            "k_query": f"https://www.youtube.com/watch?v={self.get_item().get('v')}",
            "q_auto": "1",
        }

    def __main__(self, *args, **kwargs):
        return self.main(*args, **kwargs)

    def __enter__(self, *args, **kwargs):
        return self.__main__(*args, **kwargs)

    def __exit__(self, *args, **kwargs):
        self.processed = False

    def main(self, item_no: int = 0, timeout: int = 30):
        r"""Requests for video formats and related videos
        :param item_no: (Optional) Index of query_one.vitems
        :type item_no: int
        :param timeout:  (Optional)Http request timeout
        :type timeout: int
        """
        self.processed = False
        if item_no:
            self.item_no = item_no
        okay_status, resp = utils.post(self.url, data=self.get_payload(), timeout=timeout)

        if okay_status:
            dict_data = resp.json()
            for key in dict_data.keys():
                self.__setattr__(key, dict_data.get(key))
            links = dict_data.get("links")
            self.__setattr__("video", links.get("mp4"))
            self.__setattr__("audio", links.get("mp3"))
            self.__setattr__("related", dict_data.get("related")[0].get("contents"))
            self.__setattr__("raw", dict_data)
            self.processed = True

        return self


class third_query:
    def __init__(self, query_two: second_query):
        assert query_two.processed, "Unprocessed second_query object parsed"
        self.query_two = query_two
        self.url = "https://www.y2mate.com/mates/convertV2/index"
        self.formats = ["mp4", "mp3"]
        self.qualities_plus = ["best", "worst"]
        self.qualities = {
            self.formats[0]: [
                "4k",
                "1080p",
                "720p",
                "480p",
                "360p",
                "240p",
                "144p",
                "auto",
            ]
            + self.qualities_plus,
            self.formats[1]: ["mp3", "m4a", ".m4a", "128kbps", "192kbps", "328kbps"],
        }

    def __call__(self, *args, **kwargs):
        return self.main(*args, **kwargs)

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def __str__(self):
        return """
{
    "status": "ok",
    "mess": "",
    "c_status": "CONVERTED",
    "vid": "_z-1fTlSDF0",
    "title": "Happy Birthday song",
    "ftype": "mp4",
    "fquality": "144p",
    "dlink": "https://dl165.dlmate13.online/?file=M3R4SUNiN3JsOHJ6WWQ2a3NQS1Y5ZGlxVlZIOCtyZ01tY1VxM2xzQkNMbFlyb2t1enErekxNZElFYkZlbWQ2U1g5TkVvWGplZU55T0R4K0lvcEI3QnlHbjd0a29yU3JOOXN0eWY4UmhBbE9xdmI3bXhCZEprMHFrZU96QkpweHdQVWh0OGhRMzQyaWUzS1dTdmhEMzdsYUk0VWliZkMwWXR5OENNUENOb01rUWd6NmJQS2UxaGRZWHFDQ2c0WkpNMmZ2QTVVZmx5cWc3NVlva0Nod3NJdFpPejhmeDNhTT0%3D"
}
"""

    def get_payload(self, keys):
        return {"k": keys.get("k"), "vid": self.query_two.vid}

    def main(
        self,
        format: str = "mp4",
        quality="auto",
        resolver: Optional[str] = None,
        timeout: int = 30,
    ):
        r"""
        :param format: (Optional) Media format mp4/mp3
        :param quality: (Optional) Media qualiy such as 720p
        :param resolver: (Optional) Additional format info : [m4a,3gp,mp4,mp3]
        :param timeout: (Optional) Http requests timeout
        :type type: str
        :type quality: str
        :type timeout: int
        """
        if not resolver:
            resolver = "mp4" if format == "mp4" else "mp3"
        if format == "mp3" and quality == "auto":
            quality = "128kbps"
        assert format in self.formats, f"'{format}' is not in supported formats - {self.formats}"

        assert quality in self.qualities[format], (
            f"'{quality}' is not in supported qualities - {self.qualities[format]}"
        )

        items = self.query_two.video if format == "mp4" else self.query_two.audio
        hunted = []
        if quality in self.qualities_plus:
            keys = list(items.keys())
            if quality == self.qualities_plus[0]:
                hunted.append(items[keys[0]])
            else:
                hunted.append(items[keys[len(keys) - 2]])
        else:
            for key in items.keys():
                if items[key].get("q") == quality:
                    hunted.append(items[key])
        if len(hunted) > 1:
            for entry in hunted:
                if entry.get("f") == resolver:
                    hunted.insert(0, entry)
        if hunted:

            def hunter_manager(souped_entry: dict = hunted[0], repeat_count=0):
                payload = self.get_payload(souped_entry)
                okay_status, resp = utils.post(self.url, data=payload)
                if okay_status:
                    sanitized_feedback = resp.json()
                    if sanitized_feedback.get("c_status") == "CONVERTING":
                        if repeat_count >= 4:
                            return (False, {})
                        else:
                            sleep(5)
                            repeat_count += 1
                            return hunter_manager(souped_entry)
                    return okay_status, resp
                return okay_status, resp

            okay_status, resp = hunter_manager()

            if okay_status:
                resp_data = hunted[0]
                resp_data.update(resp.json())
                return resp_data

            else:
                return {}
        else:
            return {}


class Handler:
    def __init__(
        self,
        query: str,
        author: Optional[str] = None,
        timeout: int = 30,
        confirm: bool = False,
        unique: bool = False,
        thread: int = 0,
    ):
        r"""Initializes this `class`
        :param query: Video name or youtube link
        :type query: str
        :param author: (Optional) Author (Channel) of the videos
        :type author: str
        :param timeout: (Optional) Http request timeout
        :type timeout: int
        :param confirm: (Optional) Confirm before downloading media
        :type confirm: bool
        :param unique: (Optional) Ignore previously downloaded media
        :type confirm: bool
        :param thread: (Optional) Thread the download process through `auto-save` method
        :type thread int
        """
        self.query = query
        self.author = author
        self.timeout = timeout
        self.keyword: Optional[str] = None
        self.confirm = confirm
        self.unique = unique
        self.thread = thread
        self.vitems: list[dict[str, str]] = []
        self.related: list[dict[str, str]] = []
        self.dropped: list[str] = []
        self.total = 1
        self.query_one: Optional[Any] = None
        self.saved_videos = utils.get_history()

    def __str__(self):
        return self.query

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        self.vitems.clear()
        self.total = 1

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def __filter_videos(self, entries: list) -> list:
        """Filter videos based on keyword
        :param entries: List containing dict of video id and their titles
        :type entries: list
        :rtype: list
        """
        if self.keyword:
            keyword = self.keyword.lower()
            resp = []
            for entry in entries:
                if keyword in entry.get("t").lower():
                    resp.append(entry)
            return resp

        else:
            return entries

    def __make_first_query(self):
        r"""Sets query_one attribute to `self`"""
        q_one = first_query(self.query)
        self.query_one = q_one.main(self.timeout)
        if not self.query_one.is_link:
            self.vitems.extend(self.__filter_videos(self.query_one.vitems))

    @utils.error_handler(exit_on_error=True)
    def __verify_item(self, second_query_obj: second_query) -> Tuple[bool, str]:
        video_id = second_query_obj.vid
        video_author = second_query_obj.a
        video_title = second_query_obj.title
        if video_id in self.saved_videos:
            if self.unique:
                return False, "Duplicate"
            if self.confirm:
                choice = confirm_from_user(
                    f">> Re-download : {Fore.GREEN}{video_title}{Fore.RESET} by {Fore.YELLOW}{video_author}{Fore.RESET}"
                )
                print("\n[*] Ok processing...", end="\r")
                return choice, "User's choice"
        if self.confirm:
            choice = confirm_from_user(
                f">> Download : {Fore.GREEN}{video_title}{Fore.RESET} by {Fore.YELLOW}{video_author}{Fore.RESET}"
            )
            print("\n[*] Ok processing...", end="\r")
            return choice, "User's choice"
        return True, "Auto"

    def __make_second_query(self):
        r"""Links first query with 3rd query"""
        assert self.query_one is not None, "First query failed"
        init_query_two = second_query(self.query_one)
        x = 0
        if not self.query_one.is_link:
            for video_dict in self.vitems:
                init_query_two.video_dict = video_dict
                query_2 = init_query_two.main(timeout=self.timeout)
                if query_2.processed:
                    if query_2.vid in self.dropped:
                        continue
                    if self.author and self.author.lower() not in query_2.a.lower():
                        continue
                    else:
                        yes_download, reason = self.__verify_item(query_2)
                        if not yes_download:
                            self.dropped.append(query_2.vid)
                            continue
                        self.related.extend(query_2.related)
                        yield query_2
                        x += 1
                        if x >= self.total:
                            break
                else:
                    print(f"Dropping unprocessed query_two object of index {x}")
                    yield

        else:
            query_2 = init_query_two.main(timeout=self.timeout)
            if query_2.processed:
                # self.related.extend(query_2.related)
                self.vitems.extend(query_2.related)
                self.query_one.is_link = False
                if self.total == 1:
                    yield query_2
                else:
                    for video_dict in self.vitems:
                        init_query_two.video_dict = video_dict
                        query_2 = init_query_two.main(timeout=self.timeout)
                        if query_2.processed:
                            if self.author and self.author.lower() not in query_2.a.lower():
                                continue
                            else:
                                yes_download, reason = self.__verify_item(query_2)
                                if not yes_download:
                                    self.dropped.append(query_2.vid)
                                    continue

                                self.related.extend(query_2.related)
                                yield query_2
                                x += 1
                                if x >= self.total:
                                    break
                        else:
                            yield
            else:
                yield

    def run(
        self,
        format: str = "mp4",
        quality: str = "auto",
        resolver: Optional[str] = None,
        limit: int = 1,
        keyword: Optional[str] = None,
        author: Optional[str] = None,
    ):
        r"""Generate and yield video dictionary
        :param format: (Optional) Media format mp4/mp3
        :param quality: (Optional) Media qualiy such as 720p/128kbps
        :param resolver: (Optional) Additional format info : [m4a,3gp,mp4,mp3]
        :param limit: (Optional) Total videos to be generated
        :param keyword: (Optional) Video keyword
        :param author: (Optional) Author of the videos
        :type quality: str
        :type total: int
        :type keyword: str
        :type author: str
        :rtype: object
        """
        self.author = author
        self.keyword = keyword
        self.total = limit
        self.__make_first_query()
        for query_two_obj in self.__make_second_query():
            if query_two_obj:
                self.vitems.extend(query_two_obj.related)
                yield third_query(query_two_obj).main(
                    format=format,
                    quality=quality,
                    resolver=resolver,
                    timeout=self.timeout,
                )

    def generate_filename(self, third_dict: dict, naming_format: Optional[str] = None) -> str:
        r"""Generate filename based on the response of `third_query`
        :param third_dict: response of `third_query.main()` object
        :param naming_format: (Optional) Format for generating filename based on `third_dict` keys
        :type third_dict: dict
        :type naming_format: str
        :rtype: str
        """
        fnm = (
            f"{naming_format}" % third_dict
            if naming_format
            else f"{third_dict['title']} {third_dict['vid']}_{third_dict['fquality']}.{third_dict['ftype']}"
        )

        def sanitize(nm):
            trash = [
                "\\",
                "/",
                ":",
                "*",
                "?",
                '"',
                "<",
                "|",
                ">",
                "y2mate.com",
                "y2mate com",
            ]
            for val in trash:
                nm = nm.replace(val, "")
            return nm.strip()

        return sanitize(fnm)

    def auto_save(
        self,
        dir: str = "",
        iterator: Optional[Any] = None,
        progress_bar=True,
        quiet: bool = False,
        naming_format: Optional[str] = None,
        chunk_size: int = 512,
        play: bool = False,
        resume: bool = False,
        *args,
        **kwargs,
    ):
        r"""Query and save all the media
        :param dir: (Optional) Path to Directory for saving the media files
        :param iterator: (Optional) Function that yields third_query object - `Handler.run`
        :param progress_bar: (Optional) Display progress bar
        :param quiet: (Optional) Not to stdout anything
        :param naming_format: (Optional) Format for generating filename
        :param chunk_size: (Optional) Chunk_size for downloading files in KB
        :param play: (Optional) Auto-play the media after download
        :param resume: (Optional) Resume the incomplete download
        :type dir: str
        :type iterator: object
        :type progress_bar: bool
        :type quiet: bool
        :type naming_format: str
        :type chunk_size: int
        :type play: bool
        :type resume: bool
        args & kwargs for the iterator
        :rtype: None
        """
        iterator_object = iterator or self.run(*args, **kwargs)

        for x, entry in enumerate(iterator_object):
            if self.thread:
                t1 = Thread(
                    target=self.save,
                    args=(
                        entry,
                        dir,
                        False,
                        quiet,
                        naming_format,
                        chunk_size,
                        play,
                        resume,
                    ),
                )
                t1.start()
                thread_count = x + 1
                if thread_count % self.thread == 0 or thread_count == self.total:
                    t1.join()
            else:
                self.save(
                    entry,
                    dir,
                    progress_bar,
                    quiet,
                    naming_format,
                    chunk_size,
                    play,
                    resume,
                )

    def save(
        self,
        third_dict: dict,
        dir: str = "",
        progress_bar=True,
        quiet: bool = False,
        naming_format: Optional[str] = None,
        chunk_size: int = 512,
        play: bool = False,
        resume: bool = False,
        disable_history=False,
    ):
        r"""Download media based on response of `third_query` dict-data-type
        :param third_dict: Response of `third_query.run()`
        :param dir: (Optional) Directory for saving the contents
        :param progress_bar: (Optional) Display download progress bar
        :param quiet: (Optional) Not to stdout anything
        :param naming_format: (Optional) Format for generating filename
        :param chunk_size: (Optional) Chunk_size for downloading files in KB
        :param play: (Optional) Auto-play the media after download
        :param resume: (Optional) Resume the incomplete download
        :param disable_history (Optional) Don't save the download to history.
        :type third_dict: dict
        :type dir: str
        :type progress_bar: bool
        :type quiet: bool
        :type naming_format: str
        :type chunk_size: int
        :type play: bool
        :type resume: bool
        :type disable_history: bool
        :rtype: None
        """
        if third_dict:
            assert third_dict.get("dlink"), (
                "The video selected does not support that quality, try lower qualities."
            )
            if third_dict.get("mess"):
                pass

            current_downloaded_size = 0
            current_downloaded_size_in_mb = 0.0
            filename = self.generate_filename(third_dict, naming_format)
            save_to = path.join(dir, filename)
            mod_headers: dict[str, str] = headers

            if resume:
                assert path.exists(save_to), f"File not found in path - '{save_to}'"
                current_downloaded_size = path.getsize(save_to)
                # Set the headers to resume download from the last byte
                mod_headers = {"Range": f"bytes={current_downloaded_size}-"}
                current_downloaded_size_in_mb = round(
                    current_downloaded_size / 1000000, 2
                )  # convert to mb

            resp = session.get(third_dict["dlink"], stream=True, headers=mod_headers)

            default_content_length = 0
            size_in_bytes = int(resp.headers.get("content-length", default_content_length))
            if not size_in_bytes:
                if resume:
                    raise FileExistsError(f"Download completed for the file in path - '{save_to}'")
                else:
                    raise Exception(f"Cannot download file of content-length {size_in_bytes} bytes")

            if resume:
                assert size_in_bytes != current_downloaded_size, (
                    f"Download completed for the file in path - '{save_to}'"
                )

            size_in_mb = round(size_in_bytes / 1000000, 2) + current_downloaded_size_in_mb
            chunk_size_in_bytes = chunk_size * 1024

            third_dict["saved_to"] = (
                save_to
                if any([save_to.startswith("/"), ":" in save_to])
                else path.join(getcwd(), dir, filename)
            )

            def try_play_media():
                return launch_media(third_dict["saved_to"]) if play else None

            saving_mode = "ab" if resume else "wb"
            if progress_bar:
                if not quiet:
                    print(f"{filename}")
                with tqdm(
                    total=size_in_bytes + current_downloaded_size,
                    bar_format="%s%d MB %s{bar} %s{l_bar}%s"
                    % (Fore.GREEN, size_in_mb, Fore.CYAN, Fore.YELLOW, Fore.RESET),
                    initial=current_downloaded_size,
                ) as p_bar:
                    # p_bar.update(current_downloaded_size)
                    with open(save_to, saving_mode) as fh:
                        for chunks in resp.iter_content(chunk_size=chunk_size_in_bytes):
                            fh.write(chunks)
                            p_bar.update(chunk_size_in_bytes)
                    if not disable_history:
                        utils.add_history(third_dict)
                    try_play_media()
                    return save_to
            else:
                with open(save_to, saving_mode) as fh:
                    for chunks in resp.iter_content(chunk_size=chunk_size_in_bytes):
                        fh.write(chunks)
                if not disable_history:
                    utils.add_history(third_dict)

                try_play_media()

                return save_to


mp4_qualities = [
    "4k",
    "1080p",
    "720p",
    "480p",
    "360p",
    "240p",
    "144p",
    "auto",
    "best",
    "worst",
]
mp3_qualities = ["mp3", "m4a", ".m4a", "128kbps", "192kbps", "328kbps"]
resolvers = ["m4a", "3gp", "mp4", "mp3"]
media_qualities = mp4_qualities + mp3_qualities


def launch_media(filepath):
    """
    Launch media file using default system application
    """
    try:
        if sys.platform.startswith("darwin"):  # macOS
            subprocess.call(("open", filepath))
        elif sys.platform.startswith("win"):  # Windows
            os.startfile(filepath)
        elif sys.platform.startswith("linux"):  # Linux
            subprocess.call(("xdg-open", filepath))
    except Exception as e:
        print(f"Error launching media: {e}")


def confirm_from_user(message, default=False):
    """
    Prompt user for confirmation
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}

    if default is None:
        prompt = " [y/n] "
    elif default:
        prompt = " [Y/n] "
    else:
        prompt = " [y/N] "

    while True:
        choice = input(message + prompt).lower()
        if default is not None and choice == "":
            return default
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")


# Create CLI app
app = CLI(name="ytdownloader", help="YouTube Video Downloader CLI")


@app.command()
@option("--author", help="Specify video author/channel")
@option("--timeout", type=int, default=30, help="HTTP request timeout")
@option("--confirm", is_flag=True, help="Confirm before downloading")
@option("--unique", is_flag=True, help="Ignore previously downloaded media")
@option("--thread", type=int, default=0, help="Thread download process")
@option("--format", default="mp4", help="Download format (mp4/mp3)")
@option("--quality", default="auto", help="Video quality")
@option("--limit", type=int, default=1, help="Total videos to download")
@option("--keyword", help="Filter videos by keyword")
@argument("query", help="Video name or YouTube link")
def download(query, author, timeout, confirm, unique, thread, format, quality, limit, keyword):
    """Download YouTube videos with advanced options"""

    # Create handler with parsed arguments
    handler = Handler(
        query=query, author=author, timeout=timeout, confirm=confirm, unique=unique, thread=thread
    )

    # Run download process
    handler.auto_save(format=format, quality=quality, limit=limit, keyword=keyword)


# Replace get_args function with swiftcli's argument parsing
def main():
    app.run()


if __name__ == "__main__":
    main()
