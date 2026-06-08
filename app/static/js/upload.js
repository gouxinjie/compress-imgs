(function () {
  const config = window.APP_CONFIG;
  const fileInput = document.getElementById("file-input");
  const dropTarget = document.getElementById("drop-target");
  const uploadCard = dropTarget ? dropTarget.parentElement : null;
  const uploadError = document.getElementById("upload-error");
  const taskItems = document.getElementById("task-items");
  const resultButton = document.getElementById("result-button");
  const resetButton = document.getElementById("reset-button");
  const boardTitle = document.getElementById("board-title");
  const boardSubtitle = document.getElementById("board-subtitle");
  const uploadStatusText = document.getElementById("upload-status-text");
  const uploadProgressFill = document.getElementById("upload-progress-fill");
  const uploadProgressValue = document.getElementById("upload-progress-value");
  const compressStatusText = document.getElementById("compress-status-text");
  const compressProgressFill = document.getElementById("compress-progress-fill");
  const compressProgressValue = document.getElementById("compress-progress-value");
  const doneStatusText = document.getElementById("done-status-text");
  const summaryProcessed = document.getElementById("summary-processed");
  const summaryOriginal = document.getElementById("summary-original");
  const summaryCompressed = document.getElementById("summary-compressed");
  const summarySaved = document.getElementById("summary-saved");
  const summaryRatio = document.getElementById("summary-ratio");

  if (!fileInput || !dropTarget || !uploadCard) {
    return;
  }

  const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
  const sessionRows = new Map();
  const rowOrder = [];
  const rowKeysByTaskId = new Map();
  const pendingBatchRowKeys = new Map();
  const downloadedRowKeys = new Set();
  const activeTaskIds = new Set();
  const previewMap = new Map();

  let batchCounter = 0;
  let currentTaskId = null;
  let currentTaskSnapshot = null;
  let currentUploadPercent = 0;
  let currentUploadMessage = "等待选择图片";
  let currentCompressPercent = 0;
  let currentCompressMessage = "上传完成后开始处理";
  let pollTimer = null;

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

  function setUploadProgress(percent, message) {
    currentUploadPercent = percent;
    currentUploadMessage = message;
    uploadProgressFill.style.width = `${percent}%`;
    uploadProgressValue.textContent = `${percent}%`;
    uploadStatusText.textContent = message;
  }

  function setCompressProgress(percent, message) {
    currentCompressPercent = percent;
    currentCompressMessage = message;
    compressProgressFill.style.width = `${percent}%`;
    compressProgressValue.textContent = `${percent}%`;
    compressStatusText.textContent = message;
  }

  function upsertRow(rowKey, item) {
    if (!sessionRows.has(rowKey)) {
      rowOrder.push(rowKey);
    }
    sessionRows.set(rowKey, { ...sessionRows.get(rowKey), ...item, rowKey });
  }

  function getOrderedRows() {
    return rowOrder.map((rowKey) => sessionRows.get(rowKey)).filter(Boolean);
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
        detail: item.error_message || "请稍后重试。",
      };
    }
    if (item.status === "processing") {
      return {
        icon: "/assets/icon_loader.png",
        title: "压缩中...",
        detail: "正在处理中，请稍候。",
      };
    }
    return {
      icon: "/assets/icon_doc.png",
      title: "排队中",
      detail: "等待进入压缩队列",
    };
  }

  function renderTaskRows() {
    const items = getOrderedRows();
    taskItems.innerHTML = "";

    if (!items.length) {
      taskItems.innerHTML =
        '<article class="task-row"><div class="file-cell"><strong>等待上传图片</strong></div><span>-</span><span class="status-cell"><b>暂无任务</b><small>选择图片后开始压缩</small></span><span class="dash">-</span></article>';
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "task-row";

      const statusMeta = getStatusMeta(item);
      const preview = previewMap.get(item.rowKey) || item.preview_path || "/assets/icon_image.png";
      const downloaded = downloadedRowKeys.has(item.rowKey);
      const actionMarkup = item.download_path
        ? `<a class="icon-action${downloaded ? " downloaded" : ""}" href="${item.download_path}" download data-downloadable="true" data-row-key="${item.rowKey}" title="${downloaded ? "已下载" : "下载图片"}"><img class="blend-icon" src="${downloaded ? "/assets/icon_check_circle.png" : "/assets/icon_download.png"}" alt="" width="18" height="18"></a>`
        : '<span class="dash">-</span>';

      row.innerHTML = `
        <div class="file-cell">
          <img src="${preview}" alt="">
          <div><strong>${item.filename}</strong></div>
        </div>
        <span>${formatBytes(item.original_size)}</span>
        <span class="status-cell ${item.status}">
          <span class="status-line">
            <span class="status-icon"><img class="blend-icon" src="${statusMeta.icon}" alt="" width="18" height="18"></span>
            <b>${statusMeta.title}</b>
          </span>
          <small>${statusMeta.detail}</small>
        </span>
        <span class="action-cell">${actionMarkup}</span>
      `;

      taskItems.appendChild(row);
    });
  }

  function computeSessionSummary() {
    const items = getOrderedRows();
    const summary = {
      total: items.length,
      processed: 0,
      success: 0,
      failed: 0,
      original_bytes: 0,
      compressed_bytes: 0,
      saved_bytes: 0,
    };

    items.forEach((item) => {
      summary.original_bytes += item.original_size || 0;

      if (item.status === "success" || item.status === "failed") {
        summary.processed += 1;
      }
      if (item.status === "success") {
        summary.success += 1;
        const compressed = item.compressed_size || 0;
        summary.compressed_bytes += compressed;
        summary.saved_bytes += Math.max((item.original_size || 0) - compressed, 0);
      }
      if (item.status === "failed") {
        summary.failed += 1;
      }
    });

    return summary;
  }

  function getPendingCount() {
    let total = 0;
    pendingBatchRowKeys.forEach((rowKeys) => {
      total += rowKeys.length;
    });
    return total;
  }

  function updateSummary() {
    const summary = computeSessionSummary();
    summaryProcessed.textContent = `${summary.processed} / ${summary.total}`;
    summaryOriginal.textContent = formatBytes(summary.original_bytes);
    summaryCompressed.textContent = formatBytes(summary.compressed_bytes);
    summarySaved.textContent = formatBytes(summary.saved_bytes);

    if (summary.original_bytes > 0 && summary.saved_bytes > 0) {
      const ratio = (summary.saved_bytes / summary.original_bytes) * 100;
      summaryRatio.textContent = `(${formatter.format(ratio)}%)`;
      summaryRatio.style.display = "inline";
    } else {
      summaryRatio.textContent = "";
      summaryRatio.style.display = "none";
    }
  }

  function updateBoardFromCurrentTask() {
    const sessionSummary = computeSessionSummary();
    const total = sessionSummary.total;
    const processed = sessionSummary.processed;
    const compressPercent = total ? Math.round((processed / total) * 100) : 0;
    const pendingCount = getPendingCount();

    if (!currentTaskSnapshot) {
      boardTitle.textContent = "压缩任务";
      boardSubtitle.textContent = "等待上传图片";
      setUploadProgress(0, "等待选择图片");
      setCompressProgress(0, "上传完成后开始处理");
      doneStatusText.textContent = "查看压缩结果";
      resultButton.href = "#upload";
      resultButton.setAttribute("aria-disabled", "true");
      setStepState("uploading", []);
      return;
    }

    if (currentTaskSnapshot.status === "uploading") {
      boardTitle.textContent = "上传文件";
      boardSubtitle.textContent = "正在上传文件";
      uploadStatusText.textContent =
        pendingCount < total ? `已上传 ${total - pendingCount} 个文件，本次上传 ${pendingCount} 个文件` : currentUploadMessage;
      uploadProgressFill.style.width = `${currentUploadPercent}%`;
      uploadProgressValue.textContent = `${currentUploadPercent}%`;
      setCompressProgress(compressPercent, total ? `已完成 ${processed} / ${total}` : currentCompressMessage);
      doneStatusText.textContent = "上传完成后开始压缩";
      resultButton.setAttribute("aria-disabled", "true");
      setStepState("uploading", []);
      return;
    }

    if (total > 0) {
      setUploadProgress(100, `已上传 ${total} 个文件`);
    }

    if (activeTaskIds.size) {
      boardTitle.textContent = "正在处理";
      boardSubtitle.textContent = currentTaskSnapshot.current_filename
        ? `当前处理：${currentTaskSnapshot.current_filename}`
        : activeTaskIds.size > 1
          ? `正在处理 ${activeTaskIds.size} 个任务`
          : "正在进入处理队列";
      setCompressProgress(compressPercent, `已完成 ${processed} / ${total}`);
      doneStatusText.textContent = "完成后可查看结果";
      resultButton.setAttribute("aria-disabled", "true");
      setStepState("compressing", ["uploading"]);
      return;
    }

    if (total > 0 && processed >= total) {
      boardTitle.textContent = "压缩完成";
      boardSubtitle.textContent =
        sessionSummary.failed > 0 ? "部分成功，部分失败" : "所有图片处理完成";
      setCompressProgress(100, `已完成 ${processed} / ${total}`);
      doneStatusText.textContent = "点击下载按钮获取图片";
      resultButton.setAttribute("aria-disabled", "false");
      setStepState("completed", ["uploading", "compressing"]);
      return;
    }

    boardTitle.textContent = "处理失败";
    boardSubtitle.textContent = currentTaskSnapshot.error_message || "任务未能完成";
    setCompressProgress(compressPercent || 100, currentTaskSnapshot.error_message || "请重新上传后再试");
    doneStatusText.textContent = currentTaskSnapshot.error_message || "请重新上传后再试";
    resultButton.setAttribute("aria-disabled", "true");
    setStepState("completed", ["uploading"]);
  }

  function renderAll() {
    renderTaskRows();
    updateSummary();
    updateBoardFromCurrentTask();
  }

  function revokeAllPreviews() {
    previewMap.forEach((value) => URL.revokeObjectURL(value));
    previewMap.clear();
  }

  function resetBoard() {
    currentTaskId = null;
    currentTaskSnapshot = null;
    currentUploadPercent = 0;
    currentUploadMessage = "等待选择图片";
    currentCompressPercent = 0;
    currentCompressMessage = "上传完成后开始处理";
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }

    sessionRows.clear();
    rowOrder.length = 0;
    rowKeysByTaskId.clear();
    pendingBatchRowKeys.clear();
    downloadedRowKeys.clear();
    activeTaskIds.clear();
    revokeAllPreviews();
    fileInput.value = "";
    setError("");
    renderAll();
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

  function createPendingBatch(files) {
    const batchId = `pending-${Date.now()}-${batchCounter++}`;
    const rowKeys = [];

    files.forEach((file, index) => {
      const rowKey = `${batchId}:${index}`;
      rowKeys.push(rowKey);
      previewMap.set(rowKey, URL.createObjectURL(file));
      upsertRow(rowKey, {
        batch_id: batchId,
        filename: file.name,
        stored_filename: file.name,
        status: "queued",
        original_size: file.size,
        compressed_size: null,
        ratio: null,
        download_path: null,
        preview_path: null,
        error_code: null,
        error_message: null,
      });
    });

    pendingBatchRowKeys.set(batchId, rowKeys);
    return batchId;
  }

  function markPendingBatchFailed(batchId, message) {
    const rowKeys = pendingBatchRowKeys.get(batchId) || [];
    rowKeys.forEach((rowKey) => {
      upsertRow(rowKey, {
        status: "failed",
        compressed_size: null,
        ratio: null,
        download_path: null,
        preview_path: null,
        error_code: "upload_failed",
        error_message: message,
      });
    });

    currentTaskSnapshot = {
      status: "failed",
      error_message: message,
      summary: { processed: rowKeys.length, total: rowKeys.length },
      current_filename: null,
    };

    pendingBatchRowKeys.delete(batchId);
    renderAll();
  }

  function attachTaskToPendingBatch(taskId, batchId) {
    const rowKeys = pendingBatchRowKeys.get(batchId) || [];
    rowKeysByTaskId.set(taskId, rowKeys);
    rowKeys.forEach((rowKey) => {
      upsertRow(rowKey, { task_id: taskId });
    });
    pendingBatchRowKeys.delete(batchId);
  }

  function syncTask(taskId, task) {
    const existingRowKeys = rowKeysByTaskId.get(taskId) || [];
    const resolvedRowKeys = [...existingRowKeys];

    task.items.forEach((item, index) => {
      const rowKey = resolvedRowKeys[index] || `${taskId}:${index}`;
      resolvedRowKeys[index] = rowKey;
      upsertRow(rowKey, {
        ...item,
        task_id: taskId,
      });
    });

    rowKeysByTaskId.set(taskId, resolvedRowKeys);

    if (taskId === currentTaskId) {
      currentTaskSnapshot = task;
      resultButton.href = `/result/${taskId}`;
    }

    if (task.status === "completed" || task.status === "partial_success" || task.status === "failed") {
      activeTaskIds.delete(taskId);
    }
  }

  function schedulePoll() {
    if (pollTimer || !activeTaskIds.size) {
      return;
    }
    pollTimer = window.setTimeout(pollTasks, config.pollIntervalMs);
  }

  function pollTasks() {
    pollTimer = null;
    const taskIds = Array.from(activeTaskIds);
    if (!taskIds.length) {
      return;
    }

    Promise.all(
      taskIds.map((taskId) =>
        fetch(`/api/tasks/${taskId}`)
          .then((response) => {
            if (!response.ok) {
              throw new Error("任务状态获取失败。");
            }
            return response.json();
          })
          .then((task) => syncTask(taskId, task))
      )
    )
      .then(() => {
        renderAll();
      })
      .catch((error) => {
        setError(error.message || "任务状态获取失败。");
      })
      .finally(() => {
        if (activeTaskIds.size) {
          schedulePoll();
        }
      });
  }

  function beginUpload(files) {
    const message = validateFiles(files);
    if (message) {
      setError(message);
      return;
    }

    const batchId = createPendingBatch(files);
    const totalFiles = files.length;

    currentTaskSnapshot = {
      status: "uploading",
      summary: { processed: 0, total: totalFiles },
      current_filename: null,
    };

    setError("");
    setStepState("uploading", []);
    boardTitle.textContent = "上传文件";
    boardSubtitle.textContent = `准备上传 ${totalFiles} 个文件`;
    setUploadProgress(0, `正在上传 ${totalFiles} 个文件`);
    setCompressProgress(0, "上传完成后开始处理");
    renderAll();

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/compress");

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      boardSubtitle.textContent = `正在上传 ${totalFiles} 个文件`;
      setUploadProgress(percent, `正在上传 ${totalFiles} 个文件`);
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const payload = JSON.parse(xhr.responseText);
        currentTaskId = payload.task_id;
        currentTaskSnapshot = {
          status: "queued",
          summary: { processed: 0, total: totalFiles },
          current_filename: null,
        };

        attachTaskToPendingBatch(payload.task_id, batchId);
        activeTaskIds.add(payload.task_id);
        resultButton.href = `/result/${payload.task_id}`;
        resultButton.setAttribute("aria-disabled", "true");
        setUploadProgress(100, `已上传 ${totalFiles} 个文件`);
        boardTitle.textContent = "压缩处理中";
        boardSubtitle.textContent = "正在进入压缩队列";
        setCompressProgress(0, "等待压缩开始");
        renderAll();
        schedulePoll();
      } else {
        const detail = JSON.parse(xhr.responseText || "{}").detail;
        markPendingBatchFailed(batchId, detail?.message || "上传失败，请稍后重试。");
      }
    });

    xhr.addEventListener("error", () => {
      markPendingBatchFailed(batchId, "上传失败，请检查服务是否已启动。");
    });

    xhr.send(formData);
    fileInput.value = "";
  }

  fileInput.addEventListener("change", (event) => {
    const files = Array.from(event.target.files || []);
    beginUpload(files);
  });

  taskItems.addEventListener("click", (event) => {
    const action = event.target.closest(".icon-action[data-downloadable='true']");
    if (!action) {
      return;
    }
    downloadedRowKeys.add(action.dataset.rowKey);
    renderTaskRows();
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

  resetBoard();
})();
