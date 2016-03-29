function generator_action(name, state){
    var sub_name = name;
    if (sub_name == undefined){
        sub_name = $("#sub-choose option:selected").attr("value");
    }
    console.log("sub name: ", sub_name);

    $.ajax({
            type:"post",
            url:"/generators/"+state,
            data:JSON.stringify({"sub":sub_name}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);

                if (data.ok == true){
                    if (name ==  undefined){
                        window.location.href = '/posts'
                    }else{
                        $("#state-"+sub_name).text(data.state);
                    }

                }

            }
        });
}

function prepare_for_posting(name){
    var sub_name = name;
    if (sub_name == undefined){
        sub_name = $("#sub-choose option:selected").attr("value");
    }
    console.log("sub name: ", sub_name);

    $.ajax({
            type:"post",
            url:"/generators/prepare_for_posting",
            data:JSON.stringify({"sub":sub_name}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);
                if (data.ok == true){
                        $("#"+sub_name).addClass("more-opacity");
                }

            }
        });
};

function delete_post(sub, url_hash){
    console.log(sub,url_hash);
    $.ajax({
            type:"post",
            url:"/generators/del_post",
            data:JSON.stringify({"sub":sub,"url_hash":url_hash}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);
                if (data.ok == true){
                    $("#"+url_hash).addClass("more-opacity");
                }

            }
    })
}

function delete_sub(name){
    $.ajax({
            type:"post",
            url:"/generators/del_sub",
            data:JSON.stringify({"sub_name":name}),
            contentType:    'application/json',
            dataType:       'json',
            success:function(data){
                console.log(data);
                if (data.ok == true){
                        $("."+name+"-main").addClass("more-opacity");
                        $("#"+name+"-result-info").text("Удалил везде все.");
                }

            }
        });
}
