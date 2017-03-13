from urllib.request import urlopen
from urllib.error import URLError
from json import load as jsonload
from urllib.parse import urlparse
import os

from piksi_tools.utils import sopen

INDEX_URL = 'http://downloads.swiftnav.com/index.json'

class UpdateDownloader:

  def __init__(self, root_dir=''):
    f = urlopen(INDEX_URL)
    self.index = jsonload(f)
    self.root_dir = ''
    f.close()

  def set_root_path(self, path):
    self.root_dir = path

  def download_stm_firmware(self, hwrev):
    try:
      url = self.index[hwrev]['stm_fw']['url']
      filepath = self._download_file_from_url(url)
    except KeyError:
      raise KeyError("Error downloading firmware: URL not present in index")
    except URLError:
      raise URLError("Error: Failed to download latest STM firmware from Swift Navigation's website")
    return filepath

  def download_nap_firmware(self, hwrev):
    try:
      url = self.index[hwrev]['nap_fw']['url']
      filepath = self._download_file_from_url(url)
    except KeyError:
      raise KeyError("Error downloading firmware: URL not present in index")
    except URLError:
      raise URLError("Error: Failed to download latest NAP firmware from Swift Navigation's website")
    return filepath

  def download_multi_firmware(self, hwrev):
    try:
      url = self.index[hwrev]['fw']['url']
      filepath = self._download_file_from_url(url)
    except KeyError:
      raise KeyError("Error downloading firmware: URL not present in index")
    except URLError:
      raise URLError("Error: Failed to download latest Multi firmware from Swift Navigation's website")
    return filepath

  def _download_file_from_url(self, url):
    url = url.encode('ascii')
    urlpath = urlparse(url).path
    filename = os.path.split(urlparse(url).path)[1]
    filename = os.path.join(self.root_dir, filename)
    url_file = urlopen(url)
    blob = url_file.read()
    with sopen(filename, 'wb') as f:
      f.write(blob)
    url_file.close()

    return os.path.abspath(filename)
