(function () {
  const STORAGE_KEY = "compress-imgs:downloaded-result-links";
  const actions = Array.from(document.querySelectorAll("[data-download-key]"));

  if (!actions.length) {
    return;
  }

  function readDownloadedKeys() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch (error) {
      return new Set();
    }
  }

  function writeDownloadedKeys(keys) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(keys)));
    } catch (error) {
      // ignore storage failures
    }
  }

  function applyDownloadedState(action) {
    action.classList.add("downloaded");
    action.classList.remove("downloading");
    action.dataset.downloaded = "true";
    action.dataset.downloading = "false";
    action.setAttribute("aria-disabled", "true");
    action.setAttribute("tabindex", "-1");
    action.textContent = action.dataset.downloadedText || "已下载";
    action.title = action.dataset.downloadedText || "已下载";
  }

  function applyDownloadingState(action) {
    action.classList.add("downloading");
    action.dataset.downloading = "true";
    action.setAttribute("aria-disabled", "true");
    action.textContent = action.dataset.loadingText || "下载中...";
    action.title = action.dataset.loadingText || "下载中...";
  }

  function restoreIdleState(action) {
    action.classList.remove("downloading");
    action.dataset.downloading = "false";
    action.removeAttribute("aria-disabled");
    action.textContent = action.dataset.defaultText || "下载";
    action.title = action.dataset.defaultText || "下载";
  }

  function getDownloadFilename(action, response) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match) {
      return decodeURIComponent(utf8Match[1]);
    }

    const plainMatch = disposition.match(/filename="?([^"]+)"?/i);
    if (plainMatch) {
      return plainMatch[1];
    }

    const pathname = new URL(action.href, window.location.origin).pathname;
    return decodeURIComponent(pathname.split("/").pop() || "download");
  }

  async function downloadFile(action) {
    const response = await fetch(action.href, {
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(`Download failed with status ${response.status}`);
    }

    const blob = await response.blob();
    const objectUrl = window.URL.createObjectURL(blob);
    const tempLink = document.createElement("a");
    tempLink.href = objectUrl;
    tempLink.download = getDownloadFilename(action, response);
    document.body.appendChild(tempLink);
    tempLink.click();
    tempLink.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
  }

  const downloadedKeys = readDownloadedKeys();

  actions.forEach((action) => {
    const key = action.dataset.downloadKey;
    if (!key) {
      return;
    }

    action.dataset.defaultText = action.textContent.trim();

    if (downloadedKeys.has(key)) {
      applyDownloadedState(action);
    }

    action.addEventListener("click", async (event) => {
      event.preventDefault();

      if (action.dataset.downloaded === "true") {
        return;
      }

      if (action.dataset.downloading === "true") {
        return;
      }

      applyDownloadingState(action);

      try {
        await downloadFile(action);
        downloadedKeys.add(key);
        writeDownloadedKeys(downloadedKeys);
        applyDownloadedState(action);
      } catch (error) {
        restoreIdleState(action);
      }
    });
  });
})();
