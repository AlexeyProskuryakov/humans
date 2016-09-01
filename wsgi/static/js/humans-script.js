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
//        console.log("will send... to "+name);

        $.ajax({
            type:"POST",
            url:"/humans/"+name+"/state",
            success:function(x){
//                 console.log(x);
                 if (x.human == name){
                    $("#human-live-state").text(x.state.human_state+" [process work: "+x.state.process_state.work+"]");
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

