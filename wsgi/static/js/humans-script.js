function get_human_subs(human_name, to){
    $.ajax({
        type:"get",
        url:"/humans/"+human_name+"/config",
        success:function(data){
            if (data.ok == true) {
                result = "";
                data.data.subs.forEach(function(sub){
                    result += sub+" ";
                });
                to.text(result);
            }
        }
    });
};

$("#for-human-name").change(function(e){
         var human_name = $("#for-human-name option:selected").attr("id");
         if (human_name != undefined){
            get_human_subs(human_name, $("#human-subs"));
         }

});

function show_human_live_state(){
        var name = $("#human-name").text();
        if (name == "") {
            return
        }
        $.ajax({
            type:"POST",
            url:"/humans/"+name+"/state",
            success:function(x){
                 if (x.human == name){
                    $("#human-live-state").text(x.state.human_state+" [process last tick: "+x.state.process_state+"]");
                 }
            }
        })
    }

setInterval(function() {
    show_human_live_state()
}, 5000);


function update_channel_id(name){
    var channel_id = $("#channel-id-input").val();

    $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/channel_id",
        data:           JSON.stringify({"channel_id":channel_id}),
        contentType:    'application/json',
        dataType:       'json',
        success:        function(data){
            var text = "";
            if (data.ok){
                text = "Постановлено. Загруженно "+data.loaded+" постов";
            } else{
                text = "Что-то пошло не так: "+data.error;
            }
            $("#channel-id-update-result").text(text);
        }
    })
};

function clear_errors(name){
    $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/clear_errors",
        success:        function(data){
                if (data.ok){
                    $("#errors-container").addClass("more-opacity");
                }
        }
    });
}

function clear_statistic(name){
    $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/clear_statistic",
        success:        function(data){
                if (data.ok){
                    $("#statistic").addClass("more-opacity");
                }
        }
    });
}

function clear_log(name){
    $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/clear_log",
        success:        function(data){
                if (data.ok){
                    $("#log").addClass("more-opacity");
                }
        }
    });
}

function set_counter(name, result, result_perc, threshold){
    if (result != undefined){
        $("#"+name+"-result").css("width", result_perc+"%");
        $("#"+name+"-result").text(result+" ("+result_perc+"%)");
    }
    if (threshold != undefined){
        $("#"+name+"-threshold").css("width", threshold+"%");
        $("#"+name+"-threshold").text(threshold + "%");
    }
}

function get_min_max(name){
    var minMax = $("#"+name).slider("getValue");
    return {"min":minMax[0], "max":minMax[1]};
}

function set_threshold_counters(name){
        var data = {
            "consume":get_min_max("consume"),
            "vote":get_min_max("vote"),
            "comment":get_min_max("comment")
        };
        $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/counters/set_thresholds",
        data:           JSON.stringify(data),
        contentType:    'application/json',
        dataType:       'json',
        success:        function(data){
                if (data.ok){
                    for (var key in data.counters) {
                        set_counter(key, data.counters[key], data.percents[key], data.threshold[key]);
                    }
                    location.reload();
                }
            }
        });
}

function recreate_counters(name){
        $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/counters/recreate",
        success:        function(data){
                if (data.ok){
                    for (var key in data.counters) {
                        set_counter(key, data.counters[key], data.percents[key], data.threshold[key]);
                    }
                }
        }
    });
}

function refresh_counters(name){
        $.ajax({
        type:           "post",
        url:            "/humans/"+name+"/counters",
        success:        function(data){
                if (data.ok){
                    for (var key in data.counters) {
                        set_counter(key, data.counters[key], data.percents[key], data.threshold[key]);
                    }
                }
        }
    });
}

