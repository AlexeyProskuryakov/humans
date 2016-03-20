$("#sub-choose option").click(function(e){
    console.log(e);
    var sub_name = $(e.target).attr("value");
    console.log(sub_name);
    if (sub_name == undefined){
        $("#sub-generators-form-submit").addClass("disabled");
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
                        console.log(x,el)
                        $("#choose-sub-"+x).prop('selected', true);
                    });
                    $("#related-subs").text(data.related_subs);
                    $("#key-words").text(data.key_words);
                }
                 $("#loader-gif").hide();
            }
        });
        $("#sub-generators-form-submit").removeClass("disabled");
    }
});