var refresh_sbrdt = function(sbrdt){
	$.post(
	"/subreddit/add_to_queue/"+sbrdt,
	function(){
		location.reload();
	}
	);
};


var post_change = function(fn, v_id, meth){
	$.get(
	"/post/"+meth+"/"+fn+"/"+v_id,
	function(result){
			console.log(result);
			if (result['ok'] == true){
				location.reload();
			}
		}
	);
};
var update_chart = function(name){
        console.log("starting request to chart by name ", name);
        $.get(
            "/chart/"+name,
            function(result){
                console.log("process response");

                var series = result['series'];
                var series_params = result['series_prms'];
                var info_map = result['info'];

                console.log(series);
                console.log("sp::::",series_params);
                console.log(info_map);

                var plot = $.plot("#posts-chart",
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
                            max: 200,
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
                var plot2 = $.plot("#posts-params-chart",
                    series_params,
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
                            max: 200,
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

                $("<div id='tooltip'></div>").css({
                        position: "absolute",
                        display: "none",
                        border: "1px solid #fdd",
                        padding: "2px",
                        "background-color": "#fee",
                        opacity: 0.80
                    }).appendTo("body");

                $("#posts-chart").bind("plothover", function (event, pos, item) {
                        if (item) {
                            $("#tooltip").html(info_map[item.datapoint[0]])
                                .css({top: item.pageY+5, left: item.pageX+5})
                                .fadeIn(200);
                        } else {
                            $("#tooltip").hide();
                        }
                    });

                $("#posts-chart").bind("plotclick", function (event, pos, item) {
                        if (item) {
                            plot.highlight(item.series, item.datapoint);
                        }
                });

                $("#posts-params-chart").bind("plothover", function (event, pos, item) {
                        if (item) {
                            $("#tooltip").html(info_map[item.datapoint[0]])
                                .css({top: item.pageY+5, left: item.pageX+5})
                                .fadeIn(200);
                        } else {
                            $("#tooltip").hide();
                        }
                    });

                $("#posts-params-chart").bind("plotclick", function (event, pos, item) {
                        if (item) {
                            plot2.highlight(item.series, item.datapoint);
                        }
                });

        });

}
$(function(){
    $('#load_signal').hide()
    $('.datepicker').datepicker({
         format: "dd/mm/yyyy"
    });
    console.log($('#search_load_form'));
    $('#search_load_form').submit(function(event){
        event.preventDefault();
        $('#load_signal').show()
        console.log(event);
        console.log(this);
        var msg = $('#search_load_form').serialize();
        console.log(msg);
        $.post(
            "search/load",
            msg,
            function(result){
                console.log("result:", result);
                window.location.href = "/search/result/"+result.name;
            }
        );
    });

    var name = $("#posts-chart").attr("chart_for");
    console.log("creating chart for: ", name);
    var data;
    if ((name != undefined) && (name !== "")) {
        update_chart(name);
    }

});

function start_find(sub){
    console.log(sub);
    $.ajax({
        type:"POST",
        url:"/comment_search/start/"+sub,
        success:function(x){
            console.log(x);
             $("#"+sub+"_st").text(x.state);
        }
    })
}

