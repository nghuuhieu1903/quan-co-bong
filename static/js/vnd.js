/* Vietnamese money formatting, shared by every screen.
   ------------------------------------------------------------------
   Vietnamese writes a dot every three digits (1.500.000), so a money box
   cannot be <input type="number"> - a browser reads "45.000" there as the
   decimal 45. These boxes are text inputs marked data-money instead: this
   script groups the digits as they are typed and strips the dots again on
   submit, so the server still receives 45000. helpers.parse_vnd accepts
   either shape, so the form also works with JavaScript turned off. */
(function (global) {
    'use strict';

    function group(digits) {
        return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    // keep only digits, then regroup
    function format(value) {
        var digits = String(value == null ? '' : value).replace(/\D/g, '');
        digits = digits.replace(/^0+(?=\d)/, '');     // no leading zeros
        return digits ? group(digits) : '';
    }

    function strip(value) {
        return String(value == null ? '' : value).replace(/\D/g, '');
    }

    function attach(input) {
        if (input.dataset.moneyBound) return;
        input.dataset.moneyBound = '1';
        input.value = format(input.value);

        input.addEventListener('input', function () {
            // count the digits before the caret, then put it back after the
            // same digit - otherwise inserting a dot jumps the caret to the end
            var before = strip(this.value.slice(0, this.selectionStart)).length;
            this.value = format(this.value);
            var pos = 0, seen = 0;
            while (pos < this.value.length && seen < before) {
                if (/\d/.test(this.value[pos])) seen++;
                pos++;
            }
            this.setSelectionRange(pos, pos);
        });
    }

    function init(root) {
        (root || document).querySelectorAll('input[data-money]').forEach(attach);
    }

    document.addEventListener('DOMContentLoaded', function () {
        init();
        // hand the server bare digits
        document.addEventListener('submit', function (e) {
            e.target.querySelectorAll('input[data-money]').forEach(function (i) {
                i.value = strip(i.value);
            });
        }, true);
    });

    global.VND = {format: format, strip: strip, attach: attach, init: init};
})(window);
