//var show_ae_steps_data = function(name){
//        $("#loader-gif").show();
//        var current = new Date();
//        var next = new Date(current.getTime() + 7 * 24 * 60 * 60 * 1000);
//        $.get(
//            "/ae-represent/"+name,
//            function(result){
//                var data = result['data'];
//                console.log(data);
//                $("#loader-gif").hide();
//                $("#ae-represent-container").append("<h4>"+name+"</h4>");
//                $("#ae-represent-container").append("<div id='ae-"+name+"' class='ae-represent'></div>");
//                var plot = $.plot("#ae-"+name,
//                    [data],
//                    {
//                        series: {
//                            lines: {
//                                show: false
//                            }
//                        },
//                        zoom: {interactive: true},
//                        pan: {interactive: true},
//                        xaxis: {
//                            mode: "time",
//                            minTickSize: [1, "hour"],
//                            min: current.getTime()-60*60*1000,
//                            max: next.getTime()+60*60*1000,
//                            timeformat: "%a %H:%M:%S"
//                        }
//                    }
//                );
//
//
//        });
//        console.log("end");
//}

function show_sequences(human_name){
    console.log("will show sequences for:",human_name);
    $("#loader-gif").show();
    var current = new Date();
    var next = new Date(current.getTime() + 7 * 24 * 60 * 60 * 1000);

    $.get(
        "/sequences/"+human_name,
        function(result){
            work_times = result["work"];
            posts_times = result["posts"];
            posts_passed_times = result["posts_passed"];
            console.log(result);

            var points_cfg = {
                show: true,
                radius: 1,
                fillColor: "white",
                errorbars: "x",
                xerr: {show: true, asymmetric: true, upperCap: "-", lowerCap: "-"}
		    };

            var data = [
                {color:"green", points:points_cfg, data:work_times, label:"Work time"},
                {color:"red", points:points_cfg, data:posts_times, label:"New posts"},
                {color:"blue", points:points_cfg, data:posts_passed_times, label:"Old posts"},
            ];

            $("#loader-gif").hide();
            $("#sequences-represent-container").append("<div id='sequence-flot' class='sequence-represent'></div>");
            var plot = $.plot(
                "#sequences-flot",
                data,
                {
                        series: {
                            lines: {
                                show: false
                            }
                        },
                        zoom: {interactive: true},
                        pan: {interactive: true},
                        xaxis: {
                            mode: "time",
                            minTickSize: [1, "hour"],
                            min: current.getTime()-60*60*1000,
                            max: next.getTime()+60*60*1000,
                            timeformat: "%a %H:%M:%S"
                        }
                 }
            );
        }
    );
};
