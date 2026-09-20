(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  root.OrbitNavigation=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const center=r=>({x:Number(r.left||0)+Number(r.width||0)/2,y:Number(r.top||0)+Number(r.height||0)/2});
  const overlap=(a0,a1,b0,b1)=>Math.max(0,Math.min(a1,b1)-Math.max(a0,b0));
  function spatialScore(from,to,dx,dy){
    const a=center(from),b=center(to),ox=b.x-a.x,oy=b.y-a.y;
    if(dx&&ox*dx<=1) return null;
    if(dy&&oy*dy<=1) return null;
    const primary=Math.abs(dx?ox:oy),secondary=Math.abs(dx?oy:ox);
    const lane=dx?overlap(Number(from.top||0),Number(from.top||0)+Number(from.height||0),Number(to.top||0),Number(to.top||0)+Number(to.height||0)):
      overlap(Number(from.left||0),Number(from.left||0)+Number(from.width||0),Number(to.left||0),Number(to.left||0)+Number(to.width||0));
    const distance=Math.hypot(ox,oy);
    const anglePenalty=secondary/Math.max(primary,1);
    // First prefer elements that visually share the same row/column, then the
    // smallest directional angle. This prevents Down from drifting Left/Right.
    return (lane>0?0:1_000_000)+(anglePenalty*10_000)+(secondary*5)+primary+(distance*.05);
  }
  function bestSpatialIndex(rects,currentIndex,dx,dy){
    if(!Array.isArray(rects)||!rects.length||currentIndex<0||currentIndex>=rects.length)return -1;
    const from=rects[currentIndex];let best=-1,bestScore=Infinity;
    rects.forEach((to,i)=>{if(i===currentIndex)return;const score=spatialScore(from,to,dx,dy);if(score!==null&&score<bestScore){best=i;bestScore=score;}});
    return best;
  }
  function gamepadStyle(id,configured='auto'){
    if(configured&&configured!=='auto')return configured;
    const text=String(id||'').toLowerCase();
    if(/dualsense|dualshock|playstation|sony|054c/.test(text))return 'playstation';
    if(/nintendo|switch|joy-con|joycon|pro controller/.test(text))return 'nintendo';
    return 'xbox';
  }
  function gamepadLabels(style){
    if(style==='playstation')return {accept:'✕',back:'○',search:'△',menu:'□',favorite:'L1'};
    if(style==='nintendo')return {accept:'A',back:'B',search:'X',menu:'Y',favorite:'L'};
    return {accept:'A',back:'B',search:'Y',menu:'X',favorite:'LB'};
  }
  function applyDeadzone(value,deadzone){const v=Number(value||0),d=Math.max(0,Math.min(.95,Number(deadzone||.2)));if(Math.abs(v)<=d)return 0;return Math.sign(v)*(Math.abs(v)-d)/(1-d);}
  return {center,spatialScore,bestSpatialIndex,gamepadStyle,gamepadLabels,applyDeadzone};
});
