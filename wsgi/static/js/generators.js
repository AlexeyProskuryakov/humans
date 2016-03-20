$("#sub-choose option").on('click', function(e){
    var sub_name = $(e.target).attr("value");
    if (sub_name == undefined){
        $(".sub-generator-btn").addClass("disabled");
    } else{
        $("#loader-gif").show();
        $.ajax({
            type:"post",
            url:"/generators/sub_info",
            data:JSON.stringify({"sub":sub_name}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);
                if (data.ok == true){
                    $(".gen-name").prop('selected', false);
                    data.generators.forEach(function(x, el){
                        $("#choose-sub-"+x).prop('selected', true);
                    });
                    $("#related-subs").text(data.related_subs);
                    $("#key-words").text(data.key_words);
                }
                 $("#loader-gif").hide();
            }
        });
        $(".sub-generator-btn").removeClass("disabled");
    }
});

function start_generator(name){
    var sub_name = name;
    if (sub_name == undefined){
        sub_name = $("#sub-choose option:selected").attr("value");
    }
    console.log("sub name: ", sub_name);

    $.ajax({
            type:"post",
            url:"/generators/start",
            data:JSON.stringify({"sub":sub_name}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);
                if (data.ok == true){
                   window.location.href = '/posts'
                }

            }
        });
}