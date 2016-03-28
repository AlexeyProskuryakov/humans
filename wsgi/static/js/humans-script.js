function get_human_subs(human_name, to){
    $.ajax({
        type:"post",
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

$("#human-name option").on('click', function(e){
         var human_name = $(e.target).attr("id");
         if (human_name != undefined){
            get_human_subs(human_name, $("#human-subs"));
         }

});
