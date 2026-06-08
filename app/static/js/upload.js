(function () {
  const config = window.APP_CONFIG;
  const fileInput = document.getElementById("file-input");
  const dropTarget = document.getElementById("drop-target");
  const uploadCard = dropTarget ? dropTarget.parentElement : null;
  const uploadError = document.getElementById("upload-error");
  const taskBoard = document.getElementById("task-board");
  const taskItems = document.getElementById("task-items");
  const resultButton = document.getElementById("result-button");
  const resetButton = document.getElementById("reset-button");
  const boardTitle = document.getElementById("board-title");
  const boardSubtitle = document.getElementById("board-subtitle");
  const uploadStatusText = document.getElementById("upload-status-text");
  const uploadProgressFill = document.getElementById("upload-progress-fill");
  const uploadProgressValue = document.getElementById("upload-progress-value");
  const compressStatusText = document.getElementById("compress-status-text");
  const doneStatusText = document.getElementById("done-status-text");

  const summaryProcessed = document.getElementById("summary-processed");
  const summaryOriginal = document.getElementById("summary-original");
  const summaryCompressed = document.getElementById("summary-compressed");
  const summarySaved = document.getElementById("summary-saved");

  let currentTaskId = null;
  let previewMap = new Map();
  let pollTimer = null;

  if (!fileInput || !dropTarget || !uploadCard) {
    return;
  }

  const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

  function formatBytes(value) {
    if (value == null) {
      return "-";
    }
    if (value < 1024) {
      return `${value} B`;
    }
    if (value < 1024 * 1024) {
      return `${formatter.format(value / 1024)} KB`;
    }
    return `${formatter.format(value / 1024 / 1024)} MB`;
  }

  function setError(message) {
    if (!uploadError) {
      return;
    }
    if (!message) {
      uploadError.hidden = true;
      uploadError.textContent = "";
      return;
    }
    uploadError.hidden = false;
    uploadError.textContent = message;
  }

  function setStepState(activeStep, doneSteps) {
    document.querySelectorAll(".step-card").forEach((node) => {
      const step = node.dataset.step;
      node.classList.toggle("active", step === activeStep);
      node.classList.toggle("done", doneSteps.includes(step));
    });
  }

  function renderTaskRows(items) {
    taskItems.innerHTML = "";

    if (!items.length) {
      taskItems.innerHTML = '<article class="task-row"><div class="file-cell"><strong>等待上传图片</strong></div><span>-</span><span class="status-cell"><b>暂无任务</b><small>选择图片后开始压缩</small></span><span class="dash">-</span></article>';
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "task-row";

      const statusMeta = getStatusMeta(item);
      const preview = previewMap.get(item.filename) || item.preview_path || "/assets/icon_image.png";

      row.innerHTML = `
        <div class="file-cell">
          <img src="${preview}" alt="">
          <div><strong>${item.filename}</strong></div>
        </div>
        <span>${formatBytes(item.original_size)}</span>
        <span class="status-cell ${item.status}">
          <img src="${statusMeta.icon}" alt="" width="18" height="18">
          <b>${statusMeta.title}</b>
          <small>${statusMeta.detail}</small>
        </span>
        <span class="action-cell">
          ${item.download_path ? `<a class="icon-action" href="${item.download_path}"><img src="/assets/icon_download.png" alt="" width="18" height="18"></a>` : '<span class="dash">-</span>'}
        </span>
      `;

      taskItems.appendChild(row);
    });
  }

  function getStatusMeta(item) {
    if (item.status === "success") {
      return {
        icon: "/assets/icon_check_circle.png",
        title: "压缩完成",
        detail: `${formatBytes(item.compressed_size)}（↓ ${formatter.format(item.ratio || 0)}%）`,
      };
    }
    if (item.status === "failed") {
      return {
        icon: "/assets/icon_close.png",
        title: "压缩失败",
        detail: item.error_message || "请稍后重试",
      };
    }
    if (item.status === "processing") {
      return {
        icon: "/assets/icon_loader.png",
        title: "压缩中...",
        detail: "正在处理中，请稍候",
      };
    }
    return {
      icon: "/assets/icon_doc.png",
      title: "排队中",
      detail: "等待进入压缩队列",
    };
  }

  function updateSummary(summary) {
    summaryProcessed.textContent = `${summary.processed} / ${summary.total}`;
    summaryOriginal.textContent = formatBytes(summary.original_bytes);
    summaryCompressed.textContent = formatBytes(summary.compressed_bytes);
    summarySaved.textContent = formatBytes(summary.saved_bytes);
  }

  function resetBoard() {
    currentTaskId = null;
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    resultButton.href = "#";
    resultButton.setAttribute("aria-disabled", "true");
    boardTitle.textContent = "压缩任务";
    boardSubtitle.textContent = "等待上传图片";
    uploadStatusText.textContent = "等待选择图片";
    compressStatusText.textContent = "上传完成后开始处理";
    doneStatusText.textContent = "查看压缩结果";
    uploadProgressFill.style.width = "0%";
    uploadProgressValue.textContent = "0%";
    setStepState("uploading", []);
    setError("");
    renderTaskRows([]);
    updateSummary({ processed: 0, total: 0, original_bytes: 0, compressed_bytes: 0, saved_bytes: 0 });
    previewMap.forEach((value) => URL.revokeObjectURL(value));
    previewMap = new Map();
  }

  function validateFiles(files) {
    if (!files.length) {
      return "请至少选择 1 张图片。";
    }
    if (files.length > config.maxFiles) {
      return `单次最多上传 ${config.maxFiles} 张图片。`;
    }

    let totalBytes = 0;
    for (const file of files) {
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      if (!["png", "jpg", "jpeg", "webp"].includes(ext)) {
        return "仅支持 PNG、JPG、JPEG、WEBP。";
      }
      if (file.size > config.maxFileSizeBytes) {
        return `单张图片不能超过 ${Math.round(config.maxFileSizeBytes / 1024 / 1024)} MB。`;
      }
      totalBytes += file.size;
    }

    if (totalBytes > config.maxRequestSizeBytes) {
      return `本次上传总大小不能超过 ${Math.round(config.maxRequestSizeBytes / 1024 / 1024)} MB。`;
    }

    return "";
  }

  function beginUpload(files) {
    const message = validateFiles(files);
    if (message) {
      setError(message);
      return;
    }

    previewMap.forEach((value) => URL.revokeObjectURL(value));
    previewMap = new Map();
    files.forEach((file) => previewMap.set(file.name, URL.createObjectURL(file)));

    setError("");
    setStepState("uploading", []);
    boardTitle.textContent = "上传文件";
    boardSubtitle.textContent = `准备上传 ${files.length} 个文件`;
    uploadStatusText.textContent = `正在上传 ${files.length} 个文件`;
    renderTaskRows(
      files.map((file) => ({
        filename: file.name,
        status: "queued",
        original_size: file.size,
      }))
    );

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/compress");

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      uploadProgressFill.style.width = `${percent}%`;
      uploadProgressValue.textContent = `${percent}%`;
      boardSubtitle.textContent = `正在上传 ${files.length} 个文件`;
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const payload = JSON.parse(xhr.responseText);
        currentTaskId = payload.task_id;
        resultButton.href = `/result/${currentTaskId}`;
        boardTitle.textContent = "压缩处理中";
        boardSubtitle.textContent = "正在轮询任务进度";
        compressStatusText.textContent = "正在压缩图片...";
        setStepState("compressing", ["uploading"]);
        pollTask();
        return;
      }

      const detail = JSON.parse(xhr.responseText || "{}").detail;
      setError(detail?.message || "上传失败，请稍后重试。");
    });

    xhr.addEventListener("error", () => {
      setError("上传失败，请检查服务是否启动。");
    });

    xhr.send(formData);
  }

  function pollTask() {
    if (!currentTaskId) {
      return;
    }

    fetch(`/api/tasks/${currentTaskId}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("任务状态获取失败");
        }
        return response.json();
      })
      .then((task) => {
        renderTaskRows(task.items);
        updateSummary(task.summary);

        if (task.status === "queued" || task.status === "processing") {
          boardTitle.textContent = "正在处理";
          boardSubtitle.textContent = task.current_filename ? `当前处理：${task.current_filename}` : "正在进入处理队列";
          compressStatusText.textContent = task.current_filename
            ? `正在处理 ${task.current_filename}`
            : `已完成 ${task.summary.processed} / ${task.summary.total}`;
          doneStatusText.textContent = "完成后可查看结果";
          setStepState("compressing", ["uploading"]);
          pollTimer = window.setTimeout(pollTask, config.pollIntervalMs);
          return;
        }

        if (task.status === "completed" || task.status === "partial_success") {
          boardTitle.textContent = "压缩完成";
          boardSubtitle.textContent = task.status === "partial_success" ? "部分成功，部分失败" : "所有图片处理完成";
          compressStatusText.textContent = `已完成 ${task.summary.processed} / ${task.summary.total}`;
          doneStatusText.textContent = "点击按钮查看结果";
          setStepState("completed", ["uploading", "compressing"]);
          resultButton.setAttribute("aria-disabled", "false");
          return;
        }

        boardTitle.textContent = "处理失败";
        boardSubtitle.textContent = task.error_message || "任务未能完成";
        doneStatusText.textContent = task.error_message || "请重新上传后再试";
        setStepState("completed", ["uploading"]);
      })
      .catch((error) => {
        setError(error.message || "任务状态获取失败。");
      });
  }

  fileInput.addEventListener("change", (event) => {
    const files = Array.from(event.target.files || []);
    beginUpload(files);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropTarget.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadCard.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropTarget.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadCard.classList.remove("dragover");
    });
  });

  dropTarget.addEventListener("drop", (event) => {
    const files = Array.from(event.dataTransfer?.files || []);
    beginUpload(files);
  });

  resetButton.addEventListener("click", resetBoard);
})();
