/*!
    Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
    Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
    Created By: dan@reciprocitylabs.com
    Maintained By: dan@reciprocitylabs.com
*/

(function($) {

/**
 * GGRC.RequestStore caches GGRC API requests in session or local storage.  It
 * is mostly used for generating ad-hoc fixtures to distinguish latency due to
 * service requests from latency due to UI.
 *
 * To start recording:
 *    GGRC.RequestStore.set_record(true)
 * To start replaying:
 *    GGRC.RequestStore.set_replay(true)
 * To reset (stop recording, stop replaying):
 *    GGRC.RequestStore.pause()
 * To clear all data:
 *    GGRC.RequestStore.clear()
 */
GGRC.RequestStore = function() {
  // From https://www.artandlogic.com/blog/2013/06/ajax-caching-transports-compatible-with-jquery-deferred/
  var storage = (typeof(sessionStorage) == undefined) ?
      (typeof(localStorage) == undefined) ? {
          getItem: function(key){
              return this.store[key];
          },
          setItem: function(key, value){
              this.store[key] = value;
          },
          removeItem: function(key){
              delete this.store[key];
          },
          clear: function(){
              for (var key in this.store)
              {
                  if (this.store.hasOwnProperty(key)) delete this.store[key];
              }
          },
          store:{}
      } : localStorage : sessionStorage;


  $.ajaxTransport("json", function(options, _originalOptions, _jqXHR) {
    var recording = storage.getItem("RequestStore.record"),
        replaying = storage.getItem("RequestStore.replay");

    if (_originalOptions._canonical_url) {
      //console.debug("Found re-entrant request: " + _originalOptions._canonical_url);
      return;
    }

    if (options.type !== "GET") {
      return;
    }

    var url = options.url,
        match = url.match(/^(.*)([?&])_=\d+(?:([?&])(.*))?$/);

    if (match) {
      if (match[4]) {
        url = match[1] + match[2] + match[4];
      }
      else {
        url = match[1];
      }
    }

    _originalOptions._canonical_url = url;

    return {
      send: function(headers, completeCallback) {
        var data = null;
        if (replaying) {
          data = storage.getItem("RequestStore:" + url);
          if (data) {
            console.debug('Using cache: ', url);
            setTimeout(function() {
              completeCallback(200, 'success', { json: JSON.parse(data) });
            }, 1);
          }
          else {
            console.debug('Missed cache: ', url);
          }
        }

        if (!data && (!replaying || recording)) {
          //console.debug('Using server: ', url);
          jQuery.ajax(_originalOptions).done(function(data, statusText, jqXHR) {
            if (recording) {
              console.debug('Recording: ', url);
              storage.setItem("RequestStore:" + url, JSON.stringify(data));
            }
            completeCallback(jqXHR.status, statusText, { json: data });
          }).fail(function() {
            console.debug('fail', arguments);
          });
        }
      },
      abort: function() {
        console.debug("Aborted ajax");
      }
    };
  });


  return {
    set_record: function(state) {
      if (state)
        storage.setItem("RequestStore.record", true);
      else
        storage.removeItem("RequestStore.record");
    },

    set_replay: function(state) {
      if (state)
        storage.setItem("RequestStore.replay", true);
      else
        storage.removeItem("RequestStore.replay");
    },

    clear: function() {
      storage.clear();
    },

    pause: function() {
      this.set_record(false);
      this.set_replay(false);
    }
  };
}();

})(jQuery);
