// Photometric residual of the fixed 6x6 print at the four registered MSAA sample sites.
#include <algorithm>
#include <cmath>

extern "C" void grid(
    int print_pixels, const double* print_samples, const double* gray,
    const int* pattern, int red_pixels, const double* red, int candidates,
    const double* poses, double* scores) {
    for (int candidate = 0; candidate < candidates; ++candidate) {
        const double angle = poses[3 * candidate];
        const double dx = poses[3 * candidate + 1];
        const double dy = poses[3 * candidate + 2];
        const double cosine = std::cos(angle);
        const double sine = std::sin(angle);
        double print_error = 0, red_outside = 0;
        int red_near = 0;
        for (int pixel = 0; pixel < print_pixels; ++pixel) {
            int white = 0;
            for (int sample = 0; sample < 4; ++sample) {
                const int index = 8 * pixel + 2 * sample;
                const double x0 = print_samples[index] - dx;
                const double y0 = print_samples[index + 1] - dy;
                const double x = cosine * x0 + sine * y0;
                const double y = -sine * x0 + cosine * y0;
                const int column = int(std::floor((x + .0375) / .0125));
                const int row = int(std::floor((.0375 - y) / .0125));
                const bool on_print = row >= 0 && row < 6 && column >= 0 && column < 6;
                white += on_print ? pattern[row * 6 + column] : 1;
            }
            const double residual = std::abs(gray[pixel] - white / 4.);
            print_error += std::min(residual, .40);
        }
        // Only positive red-face pixels constrain the geometry of an occluded face.
        for (int pixel = 0; pixel < red_pixels; ++pixel) {
            const double x0 = red[2 * pixel] - dx;
            const double y0 = red[2 * pixel + 1] - dy;
            const double x = cosine * x0 + sine * y0 + .130;
            const double y = -sine * x0 + cosine * y0;
            const double extent = std::max(std::abs(x), std::abs(y));
            red_outside = std::max(red_outside, extent - .035);
            red_near += extent <= .038;
        }
        scores[3 * candidate] = print_error / std::max(print_pixels, 1);
        scores[3 * candidate + 1] = red_outside;
        scores[3 * candidate + 2] = red_near;
    }
}
