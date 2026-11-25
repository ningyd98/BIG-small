// Photometric residual of the fixed 6x6 print at the four registered MSAA sample sites.
#include <cmath>
#include <algorithm>
extern "C" void grid(int n, const double* xy, const double* gray, const int* pattern,
  int nr, const double* red, int candidates, const double* poses, double* scores) {
  for(int k=0;k<candidates;k++){
    const double angle=poses[3*k],dx=poses[3*k+1],dy=poses[3*k+2];
    const double co=std::cos(angle),si=std::sin(angle);
    double total=0,passive=0; int accepted=0;
    for(int i=0;i<n;i++){
      int white=0;
      for(int j=0;j<4;j++){
        const double x0=xy[8*i+2*j]-dx,y0=xy[8*i+2*j+1]-dy;
        const double x=co*x0+si*y0, y=-si*x0+co*y0;
        int col=int(std::floor((x+.0375)/.0125)), row=int(std::floor((.0375-y)/.0125));
        white+=(row>=0&&row<6&&col>=0&&col<6)?pattern[row*6+col]:1;
      }
      const double err=std::abs(gray[i]-white/4.);
      total+=std::min(err,.40);
    }
    // Only test positive red-face evidence. Occlusion never supplies a negative face label.
    for(int i=0;i<nr;i++){
      const double x0=red[2*i]-dx,y0=red[2*i+1]-dy;
      const double x=co*x0+si*y0+.130,y=-si*x0+co*y0;
      passive=std::max(passive,std::max(std::abs(x),std::abs(y))-.035);
      accepted+=std::max(std::abs(x),std::abs(y))<=.038;
    }
    scores[3*k]=total/std::max(n,1);scores[3*k+1]=passive;scores[3*k+2]=accepted;
  }
}
