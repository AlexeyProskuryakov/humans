var show_ae_steps_data = function(name){
        console.log("starting request by name ", name);
        $("#loader-gif").show();
        $.get(
            "/ae-represent/"+name,
            function(result){
                console.log("process response");

                var series = result['series'];

                console.log(series);

                $("#loader-gif").hide();

                var plot = $.plot("#ae-represent",
                    series,
                    {
                        series: {
                            lines: {
                                show: false
                            },
                            points: {
                                show: true
                            }
                        },
                        grid: {
                            hoverable: true,
                            clickable: true
                        },
                        yaxis: {
                            min: 0,
                            max: 50,
                        },
                        zoom: {
                            interactive: true
                        },
                        pan: {
                            interactive: true
                        },
                        selection: {
                            mode: "x"
                        }
                    }
                );

//                $("<div id='tooltip'></div>").css({
//                        position: "absolute",
//                        display: "none",
//                        border: "1px solid #fdd",
//                        padding: "2px",
//                        "background-color": "#fee",
//                        opacity: 0.80
//                    }).appendTo("body");
//
//                $("#ae-represent").bind("plothover", function (event, pos, item) {
//                        if (item) {
//                            $("#tooltip").html(info_map[item.datapoint[0]])
//                                .css({top: item.pageY+5, left: item.pageX+5})
//                                .fadeIn(200);
//                        } else {
//                            $("#tooltip").hide();
//                        }
//                    });
//
//                $("#ae-represent").bind("plotclick", function (event, pos, item) {
//                        if (item) {
//                            plot.highlight(item.series, item.datapoint);
//                        }
//                });

        });
        console.log("end");

}

$("#ae-form").submit(function(e){
    e.preventDefault();
    var name = $("#ae-name").val();
    console.log("will show ae steps... for ", name);
    show_ae_steps_data(name);
});