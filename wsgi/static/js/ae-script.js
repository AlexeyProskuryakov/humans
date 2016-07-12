var show_ae_steps_data = function(name){
        $("#loader-gif").show();
        var current = new Date();
        var next = new Date(current.getTime() + 7 * 24 * 60 * 60 * 1000);
        $.get(
            "/ae-represent/"+name,
            function(result){
                var data = result['data'];
                console.log(data);
                $("#loader-gif").hide();
                $("#ae-represent-container").append("<h4>"+name+"</h4>");
                $("#ae-represent-container").append("<div id='ae-"+name+"' class='ae-represent'></div>");
                var plot = $.plot("#ae-"+name,
                    [data],
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


        });
        console.log("end");

}

$("#ae-form").submit(function(e){
    e.preventDefault();
    var name = $("#ae-name").val();
    show_ae_steps_data(name);
});