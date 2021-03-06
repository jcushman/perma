window.DOMHelpers = window.DOMHelpers || {};

DOMHelpers.setInputValue = function(domSelector, value) {
  $(domSelector).val(value);
};

DOMHelpers.removeElement = function(domSelector) {
  $(domSelector).remove();
};

DOMHelpers.changeText = function(domSelector, text) {
  $(domSelector).text(text);
};

DOMHelpers.toggleBtnDisable = function(domSelector, disableStatus) {
  // if disableStatus is false, enable.
  // if disableStatus is true, disable.
  $(domSelector).prop('disabled', disableStatus);
};

DOMHelpers.changeHTML = function(domSelector, value) {
  $(domSelector).html(value);
}

DOMHelpers.emptyElement = function(domSelector) {
  $(domSelector).empty();
}

DOMHelpers.getValue = function (domSelector) {
  return $(domSelector).val();
}

DOMHelpers.removeClass = function (domSelector, className) {
  $(domSelector).removeClass(className);
}

DOMHelpers.showElement = function (domSelector) {
  $(domSelector).show();
}

DOMHelpers.hideElement = function (domSelector) {
  $(domSelector).hide();
}

DOMHelpers.addCSS = function (domSelector, propertyName, propertyValue) {
  $(domSelector).css(propertyName, propertyValue);
}
