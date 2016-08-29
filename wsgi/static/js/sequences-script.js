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

var week = 24 * 7 * 3600 * 1000,
    hour = 3600 * 1000;


function getInitTimestamp() {
  d = new Date();
  var day = d.getDay(),
      diff = d.getDate() - day + (day == 0 ? -6:1);

  d.setDate(diff);
  d.setHours(0);
  d.setMinutes(0);
  d.setSeconds(0);
  return new Date(d).getTime();
}

function show_sequences(human_name){
    console.log("will show sequences for:",human_name);
    $("#loader-gif").show();
    var current = new Date();

    $.get(
        "/sequences/info/"+human_name,
        function(result){
            work_times = result["work"];
            console.log(result);

            var points_cfg = {
                show: true,
                radius: 1,
                fillColor: "white",
                errorbars: "x",
                xerr: {show: true, asymmetric: true, upperCap: "-", lowerCap: "-"}
		    };

            var data = [
                {color:"green", points:points_cfg, data:work_times, label:"Work time"}
            ];

            posts_times = result["posts"];
            if (posts_times != undefined){
                data.push({color:"red", points:points_cfg, data:posts_times, label:"New posts"});
            }

            posts_passed_times = result["posts_passed"];
            if (posts_passed_times != undefined){
                data.push({color:"blue", points:points_cfg, data:posts_passed_times, label:"Old posts"});
            }

            var current_point = {
                color:  "black",
                points: {
                    show:true,
                    radius:2,
                    errorbars:"y",
                    yerr:{show:true, asymmetric:false, upperCap:"-", lowerCap:"-"}
                    },
                data:[[current.getTime(), 0.75, 1, 1]],
                label:"Current time"
            };
            console.log(current_point);
            data.push(current_point);

            sequence_metadata = result["metadata"];
            if (sequence_metadata != undefined){
                $("#sequence-info").append("<h5>"+sequence_metadata+"</h5>");
            }
            $("#loader-gif").hide();

            var plot = $.plot(
                "#sequence-represent-container",
                data,
                {
                        series: {
                            lines: {
                                show: false
                            },
                            points: {
                                errorbars: "xy",
                                xerr: {
                                    show: true,
                                }
                            }
                        },
                        zoom: {
                            interactive: true,
                            trigger: "dblclick", // or "click" for single click
		                    amount: 1.1,         // 2 = 200% (zoom in), 0.5 = 50% (zoom out)
                        },
                        pan: {
                            interactive: true,
                            },
                        xaxis: {
                            zoomRange:[1,5],
                            //panRange:[0.1,10],
                            mode: "time",
                            minTickSize: [1, "minute"],
                            min: getInitTimestamp(),
                            max: getInitTimestamp() + week,
                            timeformat: "%a %H:%M"
                        },
                        yaxis:{
                            show:false,
                        }
                 }
            );
        }
    );
};
