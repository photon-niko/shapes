import cv2
import os
import pathlib
import numpy as np
from dotmap import DotMap
import imutils

from shapes39.shapes.shape import Shape


class ParserError(Exception):
    pass


class Parser:
    def __init__(self, path, debug=False):
        if not os.path.isfile(path):
            raise ParserError("Huh? Can't find that file anywhere")
        self.img = cv2.imread(path)
        if self.img is None:
            raise ParserError("That's not an image (I think)")
        self.debug_out = self.img.copy()
        if len(self.get_image_colors(self.img)) < 2:
            raise ParserError("Wtf are you trying to do?")
        self.imgray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        self.home_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        self.debug = debug
    def get_path(self, path: str):
        return os.path.join(self.home_path, path)

    def get_image_colors(self, img):
        color_index = np.unique(img, axis=0, return_inverse=True)

        ordered_color_index = []

        for i in color_index[1]:
            if len(ordered_color_index) > 0:
                if i != ordered_color_index[-1]:
                    ordered_color_index.append(i)
            else:
                ordered_color_index.append(i)

        return [color_index[0][i] for i in ordered_color_index]

    def debug_save_image(self, src, name):
        cv2.imwrite(self.get_path(name), src)

    def get_color_ranges_mask(self, colors, img):
        c_range_sum = np.zeros(self.imgray.shape, np.uint8)
        for i in range(len(colors) - 1):
            c_range = cv2.inRange(img, colors[i], colors[i + 1])
            c_range_sum = cv2.bitwise_or(c_range_sum, c_range)
            c_range = cv2.inRange(img, colors[i + 1], colors[i])
            c_range_sum = cv2.bitwise_or(c_range_sum, c_range)
            c_range = cv2.inRange(img, colors[i], colors[i])
            c_range_sum = cv2.bitwise_or(c_range_sum, c_range)
            c_range = cv2.inRange(img, colors[i + 1], colors[i + 1])
            c_range_sum = cv2.bitwise_or(c_range_sum, c_range)

        return c_range_sum

    def get_color_ranges_mask2(self, colors, img):
        c_range_sum = np.zeros(self.imgray.shape, np.uint8)
        for i in range(len(colors)):
            c_range = cv2.inRange(img, colors[i], colors[i])
            c_range_sum = cv2.bitwise_or(c_range_sum, c_range)

        return c_range_sum

    def clean_contours_touching_edges(self, img):
        cnt, _ = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        img_copy = img.copy()

        for c in cnt:
            x, y, w, h = cv2.boundingRect(c)
            if x == 0 or y == 0 or x + w == img.shape[0] or y + h == img.shape[1]:
                cv2.drawContours(img_copy, [c], -1, 0, cv2.FILLED)

        return img_copy

    def get_masks(self):
        (img_width, img_height, _) = self.img.shape

        bottom_edge = self.img[img_height - 1, 0 : img_width - 1]

        bg_colors = self.get_image_colors(bottom_edge)

        if len(bg_colors) == 1:
            bg_colors.append(bg_colors[0])
        bg_range_sum = self.get_color_ranges_mask(bg_colors, self.img)

        bg_mask = cv2.bitwise_not(bg_range_sum)

        # bg_masked_img = cv2.bitwise_and(self.img, self.img, mask=bg_mask)
        # leaving this here to remember how to do this

        left_edge = self.img[0 : img_height - 1, 0]
        right_edge = self.img[0 : img_height - 1, img_width - 1]

        edge_colors = [self.get_image_colors(e) for e in [left_edge, right_edge]]

        shape_colors = []
        path_colors = []
        for c in edge_colors[0]:
            if not (bg_colors == c).all(axis=1).any():
                shape_colors.append(c)

        for c in edge_colors[1]:
            if not (bg_colors == c).all(axis=1).any():
                if (shape_colors == c).all(axis=1).any():
                    raise ParserError("Shape color can't be the same as path color")
                path_colors.append(c)

        for g in [shape_colors, path_colors]:
            if len(g) < 1:
                raise ParserError("Shape colors or path colors not specified")

        shape_mask = self.get_color_ranges_mask(shape_colors, self.img)
        path_mask = self.get_color_ranges_mask(path_colors, self.img)

        shape_mask_cleaned = self.clean_contours_touching_edges(shape_mask)
        shape_mask_cleaned = Parser.clean_holes(shape_mask_cleaned)

        path_mask_cleaned = self.clean_contours_touching_edges(path_mask)
        path_mask_cleaned = Parser.clean_holes(path_mask_cleaned)

        if self.debug:
            self.debug_save_image(shape_mask_cleaned, "shape.png")
            self.debug_save_image(path_mask_cleaned, "path.png")
            self.debug_save_image(bg_mask, "back.png")

        masks = {"shape": shape_mask_cleaned, "path": path_mask_cleaned, "bg": bg_mask}
        mask_map = DotMap(masks)
        return mask_map

    @staticmethod
    def clean_holes(img, kernel_size=2):
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

    @staticmethod
    def get_circles(img):
        circles = cv2.HoughCircles(
            image=img,
            method=cv2.HOUGH_GRADIENT,
            dp=1.5,
            minDist=100,
            param1=100,
            param2=35,
            maxRadius=0,
        )

        if circles is not None:
            for c in circles[0]:
                cv2.circle(img, (int(c[0]), int(c[1])), int(c[2]), (0, 255, 0), 3)
                cv2.circle(img, (int(c[0]), int(c[1])), 10, (0, 255, 0), -10)
                pass

        return circles

    @staticmethod
    def crop_contour(cnt, img):
        _, _, width, height = cv2.boundingRect(cnt)

        cnt_list = []

        for p in cnt:
            cnt_list.append([p[0][0], p[0][1]])

        cnt_list = np.array(cnt_list)

        cnt_list = cnt_list - cnt_list.min(axis=0)
        mask = np.zeros(img.shape, np.uint8)
        cv2.drawContours(mask, [cnt_list], -1, (255, 255, 255), -1, cv2.LINE_AA)

        return mask[0:height, 1:width]

    @staticmethod
    def mask_contour(cnt, img):
        cnt_list = []

        for p in cnt:
            cnt_list.append([p[0][0], p[0][1]])

        cnt_list = np.array(cnt_list)

        mask = np.zeros(img.shape, np.uint8)
        cv2.drawContours(mask, [cnt_list], -1, (255, 255, 255), -1)

        return mask

    @staticmethod
    def check_is_circle(cnt, img, i):
        _, _, width, height = cv2.boundingRect(cnt)

        cropped = Parser.crop_contour(cnt, img)

        rect = cv2.minAreaRect(cnt)

        cropped2 = imutils.rotate_bound(cropped[0:height, 1:width], rect[2] - 90)

        contours_rot, _ = cv2.findContours(
            cropped2, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        cropped2 = Parser.crop_contour(contours_rot[0], cropped2)

        width_cr, height_cr = cropped.shape

        if width_cr > height_cr:
            cropped2 = cv2.resize(cropped2, (height_cr, height_cr))
        else:
            cropped2 = cv2.resize(cropped2, (width_cr, width_cr))

        circles = Parser.get_circles(cropped)
        circles2 = Parser.get_circles(cropped2)

        perimeter = cv2.arcLength(cnt, True)
        hull = cv2.convexHull(cnt)
        hull_perimeter = cv2.arcLength(hull, True)

        roughness = perimeter / hull_perimeter

        # cv2.imwrite(f"cropped/{i}a.png", cropped)
        # cv2.imwrite(f"cropped/{i}.png", cropped2)

        return (circles2 is not None or circles is not None) and roughness < 2

    @staticmethod
    def dilate(img, kernel_size=2, iterations=1):
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.dilate(img, kernel, iterations=iterations)

    @staticmethod
    def erode(img, kernel_size=2, iterations=1):
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.erode(img, kernel, iterations=iterations)

    def get_shapes(self, contours, hierarchy, mask):
        shapes = []

        for i, cnt in enumerate(contours):
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.023 * peri, True)

            shape = None

            if Parser.check_is_circle(cnt, mask, i):
                shape = Shape(cnt, True, center=Parser.contour_center(approx))
                shape.points = approx
                if self.debug:
                    cv2.drawContours(self.debug_out, [cnt], -1, (0, 0, 255), thickness=10)
            else:
                shape = Shape(cnt, False, center=Parser.contour_center(approx))
                shape.points = approx


            shapes.append(shape)

        for i, _ in enumerate(contours):

            if hierarchy[0][i][3] != -1:
                shapes[hierarchy[0][i][3]].add_inside(shapes[i])
                shapes[i].is_hole = True
                shapes[i].outer = shapes[hierarchy[0][i][3]]

        return shapes

    def get_no_hole_shapes(self, shapes):
        no_holes ={}
        for i, shape in enumerate(shapes):
            no_holes[i] = shape
        return no_holes

    def get_connections(self, path_contours, shapes, masks):
        connections = {}

        for i, cnt in enumerate(path_contours):
            path_cnt_mask = Parser.mask_contour(cnt, masks.path)
            fused = cv2.bitwise_or(path_cnt_mask, masks.shape)
            clean_fused = Parser.clean_holes(fused)

            fused_contours, _ = cv2.findContours(
                clean_fused, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )

            for j, fused_cnt in enumerate(fused_contours):
                fused_cnt_mask = Parser.mask_contour(fused_cnt, clean_fused)
                fused_cnt_and_path_cnt = cv2.bitwise_and(fused_cnt_mask, path_cnt_mask)

                if len(np.unique(fused_cnt_and_path_cnt)) > 1:
                    path_cnt_dilate = Parser.dilate(path_cnt_mask, 2)


                    connected_shapes = cv2.subtract(fused_cnt_mask, path_cnt_dilate)

                    connected_shapes_contours, _ = cv2.findContours(
                        connected_shapes, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                    )
                    for k, connected_cnt in enumerate(connected_shapes_contours):
                        for (l, shape) in shapes.items():
                            if shape.outer is None:

                                shape_and_connected = cv2.bitwise_and(
                                    Parser.mask_contour(shape.contour, self.img),
                                    Parser.mask_contour(connected_cnt, self.img),
                                )

                                if np.any(shape_and_connected==255):
                                    if i not in connections.keys():
                                        connections[i] = [l]
                                    else:
                                        connections[i].append(l)

        return connections

    @staticmethod
    def contour_avg(cnt):
        M = cv2.moments(cnt)
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return (cX, cY)

    @staticmethod
    def contour_center(cnt):
        cx = 0
        cy = 0
        for p in cnt:
            cx += p[0][0]
            cy += p[0][1]
        cx = int(cx/len(cnt))
        cy = int(cy/len(cnt))
        return (cx,cy)

    def parse_shapes(self):
        masks = self.get_masks()

        shape_contours, shape_hierarchy = cv2.findContours(
            masks.shape, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        path_contours, _ = cv2.findContours(
            masks.path, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        shapes = self.get_shapes(shape_contours, shape_hierarchy, masks.shape)

        connections = self.get_connections(path_contours, self.get_no_hole_shapes(shapes), masks)

        for k in connections.keys():
            for i, si in enumerate(connections[k]):
                for j, sj in enumerate(connections[k]):
                    if si != sj:
                        shape_and_con = cv2.bitwise_and(
                            Parser.mask_contour(shapes[si].contour, masks.shape),
                            Parser.dilate(
                                Parser.mask_contour(path_contours[k], masks.path),
                                kernel_size=5,
                            ),
                        )

                        shape_and_con_to = cv2.bitwise_and(
                            Parser.mask_contour(shapes[sj].contour, masks.shape),
                            Parser.dilate(
                                Parser.mask_contour(path_contours[k], masks.path),
                                kernel_size=5,
                            ),
                        )

                        s_and_c_contours, _ = cv2.findContours(
                            shape_and_con, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                        )

                        s_and_c_t_contours, _ = cv2.findContours(
                            shape_and_con_to, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                        )
                        connecting_point = Parser.contour_center(s_and_c_contours[0])
                        connecting_point_to = Parser.contour_center(s_and_c_t_contours[0])
                        shapes[si].connect_shape(k, shapes[sj], connecting_point, connecting_point_to)
                        if self.debug:
                            cv2.circle(self.debug_out, connecting_point_to, 40, (0,0,255))

        if self.debug:
            for s in shapes:
                if s.circular:
                    cv2.drawContours(
                        self.debug_out, [s.contour], -1, (0, 255, 0), thickness=10
                    )
            self.debug_save_image(self.debug_out, "out.png")

            for i, s in enumerate(shapes):
                if s.outer is None:
                    for p in s.points:

                        cv2.circle(self.debug_out, p[0], 5, (255, 0, 0), -1)
                    self.debug_save_image(self.debug_out, "out.png")
                    cv2.putText(
                        self.debug_out,
                        f"{s.get_shape_type().name}",
                        Parser.contour_avg(s.contour),
                        cv2.FONT_HERSHEY_PLAIN,
                        2,
                        (0, 0, 0),
                        2,
                    )
                for k in s.connecteds.keys():
                    for i, c in enumerate(s.connecteds[k][1]):
                        thickness = 20//(i+1)
                        cv2.line(
                            self.debug_out,
                            s.connecteds[k][0],
                            c[1],
                            (100+np.random.random()*100, (255 / len(path_contours)) * k, 0),
                            thickness,
                        )

            self.debug_save_image(self.debug_out, "seen.png")

        return shapes