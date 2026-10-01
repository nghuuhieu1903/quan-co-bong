/* "Chụp ảnh" button next to image file inputs.
   ------------------------------------------------------------------
   Any <input type="file" data-camera> keeps its normal "Choose File" control
   and gains a button that opens the device camera. The photo is shrunk first:
   a phone camera shot is routinely 4-10MB, over the 5MB per-file cap the
   server enforces (helpers.MAX_UPLOAD_SIZE), and the shop only ever shows
   these at a few hundred pixels. The result is dropped into the real input,
   so the form submits exactly as if a file had been chosen. The button's
   visibility is pure CSS (.camera-btn in modern.css). */
(function () {
    var MAX_SIDE = 1600;
    var QUALITY = 0.85;

    function shrink(file) {
        return new Promise(function (resolve) {
            var url = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () {
                URL.revokeObjectURL(url);
                var scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
                var canvas = document.createElement('canvas');
                canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
                canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
                canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                canvas.toBlob(function (blob) {
                    resolve(blob
                        ? new File([blob], 'camera_' + Date.now() + '.jpg', { type: 'image/jpeg' })
                        : file);
                }, 'image/jpeg', QUALITY);
            };
            img.onerror = function () { URL.revokeObjectURL(url); resolve(file); };
            img.src = url;
        });
    }

    function enhance(input) {
        var camera = document.createElement('input');
        camera.type = 'file';
        camera.accept = 'image/*';
        camera.setAttribute('capture', 'environment');
        camera.hidden = true;

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-outline camera-btn';
        button.innerHTML = '<i class="fas fa-camera"></i> Chụp ảnh';
        button.addEventListener('click', function () { camera.click(); });

        camera.addEventListener('change', function () {
            if (!camera.files.length) return;
            shrink(camera.files[0]).then(function (photo) {
                // a multi-image field keeps what was already picked, so several
                // photos can be taken one after another
                var files = input.multiple ? Array.prototype.slice.call(input.files) : [];
                var transfer = new DataTransfer();
                files.concat(photo).forEach(function (f) { transfer.items.add(f); });
                input.files = transfer.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                camera.value = '';
            });
        });

        input.insertAdjacentElement('afterend', button);
        button.insertAdjacentElement('afterend', camera);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof DataTransfer === 'undefined' || typeof File === 'undefined') return;
        document.querySelectorAll('input[type="file"][data-camera]').forEach(enhance);
    });
})();
