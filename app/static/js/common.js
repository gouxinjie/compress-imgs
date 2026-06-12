(function () {
  const toast = document.getElementById("nav-toast");
  const toastTitle = document.getElementById("nav-toast-title");
  const toastMessage = document.getElementById("nav-toast-message");
  const triggerNodes = document.querySelectorAll("[data-toast-key]");
  const fileExpireMinutes = Number(document.body?.dataset.fileExpireMinutes || "30");
  const toastMap = {
    privacy: {
      title: "\u5b89\u5168\u9690\u79c1",
      message: `\u6587\u4ef6\u4ec5\u4e34\u65f6\u5b58\u50a8\uff0c${fileExpireMinutes} \u5206\u949f\u540e\u81ea\u52a8\u6e05\u7406\uff0c\u4e0d\u4f1a\u957f\u671f\u4fdd\u7559\u3002`,
    },
    help: {
      title: "\u4f7f\u7528\u5e2e\u52a9",
      message: "\u62d6\u62fd\u6216\u9009\u62e9\u56fe\u7247\u540e\u5f00\u59cb\u538b\u7f29\uff0c\u5904\u7406\u5b8c\u6210\u540e\u53ef\u4e0b\u8f7d\u5355\u56fe\u6216 ZIP\u3002",
    },
  };

  if (!toast || !toastTitle || !toastMessage || !triggerNodes.length) {
    return;
  }

  let hideTimer = null;
  let hideCompleteTimer = null;
  let enterCompleteTimer = null;
  const enterDurationMs = 360;
  const exitDurationMs = 260;

  function showToast(title, message) {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (hideCompleteTimer) {
      clearTimeout(hideCompleteTimer);
      hideCompleteTimer = null;
    }
    if (enterCompleteTimer) {
      clearTimeout(enterCompleteTimer);
      enterCompleteTimer = null;
    }

    toastTitle.textContent = title;
    toastMessage.textContent = message;
    toast.hidden = false;
    toast.classList.remove("is-entering");
    toast.classList.remove("is-hiding");
    toast.classList.remove("is-visible");

    // Force a fresh animation cycle so repeated taps still slide in from the right.
    void toast.offsetWidth;

    toast.classList.add("is-visible");
    toast.classList.add("is-entering");
    enterCompleteTimer = window.setTimeout(() => {
      toast.classList.remove("is-entering");
      enterCompleteTimer = null;
    }, enterDurationMs);

    hideTimer = window.setTimeout(() => {
      toast.classList.remove("is-entering");
      toast.classList.remove("is-visible");
      toast.classList.add("is-hiding");
      hideCompleteTimer = window.setTimeout(() => {
        toast.hidden = true;
        toast.classList.remove("is-hiding");
        hideCompleteTimer = null;
      }, exitDurationMs);
      hideTimer = null;
    }, 2200);
  }

  triggerNodes.forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      const toastContent = toastMap[node.dataset.toastKey] || null;
      if (!toastContent) {
        return;
      }
      showToast(toastContent.title, toastContent.message);
    });
  });
})();
