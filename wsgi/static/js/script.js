function start_find_comments(sub){
    console.log(sub);
    $.ajax({
        type:"POST",
        url:"/comment_search/start/"+sub,
        success:function(x){
             console.log(x);
             $("#"+sub+"-st").text(x.state);
        }
    })
}


function show_human_live_state(){
    var name = $("#human-name").text();
    console.log("will send... to "+name);
    $.ajax({
        type:"POST",
        url:"/humans/"+name+"/state",
        success:function(x){
             console.log(x);
             if (x.human == name){
                $("#human-live-state").text(x.state);
             }
        }
    })
}

setInterval(function() {
  show_human_live_state()
}, 1000);