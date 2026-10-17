function diffOps(before,after){
 const a=before.trimEnd().split("\n"),b=after.trimEnd().split("\n");
 const d=Array.from({length:a.length+1},()=>new Uint16Array(b.length+1));
 for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)d[i][j]=a[i]===b[j]?d[i+1][j+1]+1:Math.max(d[i+1][j],d[i][j+1]);
 const ops=[];let i=0,j=0;
 while(i<a.length||j<b.length){if(i<a.length&&j<b.length&&a[i]===b[j]){ops.push({type:" ",text:a[i],old:i+1,new:j+1});i++;j++;}
 else if(i<a.length&&(j===b.length||d[i+1][j]>=d[i][j+1])){ops.push({type:"-",text:a[i],old:i+1,new:j+1});i++;}
 else {ops.push({type:"+",text:b[j],old:i+1,new:j+1});j++;}}
 const changed=ops.map((x,k)=>x.type!==" "?k:-1).filter(x=>x>=0),ranges=[];
 for(const k of changed){const start=Math.max(0,k-3),end=Math.min(ops.length,k+4);if(ranges.length&&start<=ranges[ranges.length-1][1])ranges[ranges.length-1][1]=Math.max(end,ranges[ranges.length-1][1]);else ranges.push([start,end]);}
 return ranges.map(([lo,hi])=>{const part=ops.slice(lo,hi),oldCount=part.filter(x=>x.type!=="+").length,newCount=part.filter(x=>x.type!=="-").length;return "@@ -"+part[0].old+","+oldCount+" +"+part[0].new+","+newCount+" @@\n"+part.map(x=>x.type+x.text).join("\n")+"\n";}).join("");
}
const p=load("r176_frozen_plan_parsed"),paths=p.scope.editable_scripts;
const data=[[paths[0],load("r176_old_metadata_source"),load("r176_final_metadata_source")],[paths[1],load("r176_old_runner_source"),load("r176_final_runner_source")]];
const bodies=data.map(([path,before,after])=>({path,hunks:diffOps(before,after)}));
store("r176_full_script_diff_text",bodies.map(x=>"--- "+x.path+" (R175 preserved draft)\n+++ "+x.path+" (R176 candidate)\n"+x.hunks).join(""));
const patch="*** Begin Patch\n"+bodies.map(x=>"*** Update File: "+x.path+"\n"+x.hunks).join("")+"*** End Patch";
store("r176_exact_script_patch",patch);
const result=await tools.apply_patch(patch);store("r176_script_implementation_actual",result);text({result,paths});
