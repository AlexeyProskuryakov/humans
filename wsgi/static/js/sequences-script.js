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

function show_sequences(human_name, withLoader){
    if (withLoader){
        $("#loader-gif").show();
    }

    $.get(
        "/sequences/info/"+human_name,
        function(result){
            work_times = result["work"];
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

            data.push({color:"red", points:points_cfg, data:result["posts"], label:"New posts"});
            data.push({color:"blue", points:points_cfg, data:result["posts_passed"], label:"Old posts"});
            data.push({color:"black", points:points_cfg, data:result["real"], label:"Real passed"});


            var current_point = {
                color:  "black",
                points: {
                    show:true,
                    radius:2,
                    errorbars:"y",
                    yerr:{show:true, asymmetric:false, upperCap:"-", lowerCap:"-"}
                    },
                data:[result['current']]
            };
            data.push(current_point);

            $("#sequence-metadata").text(result["metadata"]);

            var counters = result["counters"];
            $("#sequence-metadata").append("<hr> Next important after: <b>"+ counters['next_important'] +"</b> noise posts <br>");
            $("#sequence-metadata").append(" Next noise: <b>"+result["next_times"]["noise"]+"</b> <br> Next important: <b>" +result["next_times"]["important"]+"</b>");

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
		                    amount: 1.5,         // 2 = 200% (zoom in), 0.5 = 50% (zoom out)
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
                            max: getInitTimestamp() + week + hour * 5,
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
