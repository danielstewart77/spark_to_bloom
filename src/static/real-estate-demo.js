(function () {
  "use strict";

  var currentStep = "portfolio";
  var storedCount = 3;

  function showStep(step) {
    currentStep = step;
    document.querySelectorAll("[data-workflow-step]").forEach(function (screen) {
      var active = screen.dataset.workflowStep === step;
      screen.classList.toggle("is-active", active);
      screen.hidden = !active;
    });
    document.querySelectorAll("[data-step-target]").forEach(function (button) {
      button.classList.toggle("is-active", button.dataset.stepTarget === step);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function updateCounts() {
    document.getElementById("capture-count").textContent = storedCount + " stored";
    document.getElementById("stored-count").textContent = String(storedCount);
    document.getElementById("process-asset-count").textContent = String(storedCount);
  }

  function addImagePreview(file) {
    var preview = document.getElementById("capture-preview");
    var figure = document.createElement("figure");
    var image = document.createElement("img");
    var caption = document.createElement("figcaption");
    image.src = URL.createObjectURL(file);
    image.alt = file.name;
    caption.textContent = document.querySelector(".re-tag.is-selected").textContent + " · new capture";
    figure.appendChild(image);
    figure.appendChild(caption);
    preview.appendChild(figure);
  }

  document.querySelectorAll("[data-start-property]").forEach(function (button) {
    button.addEventListener("click", function () { showStep("capture"); });
  });

  document.querySelectorAll("[data-go]").forEach(function (button) {
    button.addEventListener("click", function () { showStep(button.dataset.go); });
  });

  document.querySelectorAll("[data-step-target]").forEach(function (button) {
    button.addEventListener("click", function () { showStep(button.dataset.stepTarget); });
  });

  document.querySelectorAll(".re-tag").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll(".re-tag").forEach(function (tag) { tag.classList.remove("is-selected"); });
      button.classList.add("is-selected");
    });
  });

  document.getElementById("camera-input").addEventListener("change", function (event) {
    Array.from(event.target.files || []).forEach(function (file) {
      addImagePreview(file);
      storedCount += 1;
    });
    updateCounts();
  });

  document.getElementById("document-input").addEventListener("change", function (event) {
    var count = (event.target.files || []).length;
    if (count) {
      document.getElementById("capture-note").value = count + " document" + (count === 1 ? "" : "s") + " attached to this session.";
    }
  });

  document.getElementById("voice-note-button").addEventListener("click", function () {
    var button = this;
    var status = document.getElementById("voice-note-status");
    if (button.classList.contains("is-recording")) {
      button.classList.remove("is-recording");
      status.textContent = "Note saved · 8 sec";
      document.getElementById("capture-note").value = "Need a closer shot of the second Daikin unit before we leave.";
      return;
    }
    button.classList.add("is-recording");
    status.textContent = "Recording · tap to save";
  });

  document.querySelector("[data-finish-capture]").addEventListener("click", function () {
    showStep("process");
  });

  document.getElementById("process-button").addEventListener("click", function () {
    var processButton = this;
    var jobs = ["extract", "consolidate", "draft"];
    processButton.disabled = true;
    processButton.textContent = "Skippy is processing…";
    jobs.forEach(function (jobName, index) {
      window.setTimeout(function () {
        var job = document.querySelector('[data-job="' + jobName + '"]');
        job.classList.add("is-complete");
        job.querySelector(".re-job-icon").textContent = "✓";
        job.querySelector("em").textContent = "Complete";
        if (index === jobs.length - 1) {
          processButton.hidden = true;
          document.getElementById("review-button").hidden = false;
        }
      }, 450 * (index + 1));
    });
  });

  document.querySelectorAll("[data-review-action='accept']").forEach(function (button) {
    button.addEventListener("click", function () {
      var card = button.closest(".re-review-card");
      card.classList.add("is-accepted");
      button.textContent = "Accepted";
      button.disabled = true;
    });
  });

  document.querySelector("[data-generate-dossier]").addEventListener("click", function () {
    showStep("dossier");
  });

  document.querySelector("[data-open-dossier]").addEventListener("click", function () {
    showStep("dossier");
  });

  window.realEstateDemo = { showStep: showStep, getCurrentStep: function () { return currentStep; } };
})();
